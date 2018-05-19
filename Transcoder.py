import argparse, os, uuid, tempfile, shutil, subprocess, glob, sys, logging
import ConfigContainer, Scanner, MediaProcessor
from pymediainfo import MediaInfo

class Transcoder(MediaProcessor.MediaProcessor):
    @MediaProcessor.exception_logger
    def BuildFFMPEGCommands(self, path, mediainfo, codec, crf, speed, options=None):
        basename = os.path.basename(path)
        temp_file = os.path.join(self.temp_dir, os.path.splitext(basename)[0] + '.mkv')

        # Setup our ffmpeg command
        base_cmd = ['nice', '-n20', self.config.FFMPEG_PATH, '-y'] + self.SelectDecodeCommand(mediainfo, codec, options=options) + [path]
        in_filter_graph = []
        map_cmd = ['-map', '0:v', '-map', '0:a', '-c', 'copy']
        encode_cmd = self.SelectEncodeCommand(mediainfo, codec, crf, speed, options=options)
        interlace_cmd = []
        out_filter_graph = []
        sub_cmd = []

        # Check if we are transcoding a portion of the content
        if options and 'start_timestamp' in options:
            base_cmd.extend(['-ss', options['start_timestamp']])
        if options and 'duration' in options:
            base_cmd.extend(['-t', options['duration']])

        hw_decode = '-hwaccel' in base_cmd
        hw_encode = 'nvenc' in codec

        # Need to offload the frames from the GPU if we are a using a software encoder
        if hw_decode and not hw_encode and not 'copy' == codec:
            in_filter_graph.extend(['-vf', 'hwdownload,format=nv12'])

        # See if we want to convert the pixel format
        if hw_decode and hw_encode and 'pix_fmt' in options:
                in_filter_graph.extend(['-vf', 'scale_npp=format=' + options['pix_fmt']])
        elif 'pix_fmt' in options:
            if(len(in_filter_graph) == 0):
                in_filter_graph.extend(['-vf', 'format=' + options['pix_fmt']])
            else:
                in_filter_graph[-1].append(',format=' + options['pix_fmt'])

        # Analyze the media to determine what other processing we need to do
        for track in mediainfo.tracks:
            # Deinterlace content if it is interlaced
            if (track.track_type == "Video" and track.scan_type != "Progressive"):
                logging.info("Metadata suggests this is interlaced content, running detect and deinterlace filter chain")
                if hw_decode:
                    interlace_cmd =  ['-deint', 'adaptive']
                else:
                    interlace_cmd =  ['-vf', 'idet,yadif=mode=1:deint=interlaced']
            # Remove non-english subtitles, burn in PGS-type subtitles that are "always-on"
            elif (track.track_type == "Text"):
                if(track.language is not None and track.language != 'en'):
                    sub_cmd = sub_cmd + ['-map','-0:s:' + str(track.stream_identifier)]
                    logging.info("Removing non-english subtitle. Stream ID: %s, Language: %s" % (track.stream_identifier, track.language))
                elif(track.language == 'en' and track.format == 'PGS' and (track.default == 'Yes' or track.forced == 'Yes')):
                    if(len(out_filter_graph) != 0):
                        raise Exception("This script only supports burning in one subtitle track, multiple tracks found!")

                    # Burn these subtitles in
                    out_filter_graph = ['-filter_complex', '[0:v][0:s:' + str(track.stream_identifier) + ']overlay[v]', '-map', '-0:s']
                    #'[0:v]fifo[fifo_v];[0:s:' + str(track.stream_identifier) + ']fifo[fifo_s];[fifo_v][fifo_s]overlay[v]'] + sub_cmd
                    map_cmd[1] = '[v]'
                    logging.info("Burning default or forced subtitles in. Stream ID: %s, Language: %s, Default: %s, Forced: %s, Format: %s" % (track.stream_identifier, track.language, track.default, track.forced, track.format))

        # Build the full command
        cmd = base_cmd + in_filter_graph + map_cmd + interlace_cmd + encode_cmd + out_filter_graph + [temp_file]

        # Add the transcode command to the list of commands to run
        cmds = [cmd]

        # Add the sub command to the list of commands to run
        if len(sub_cmd) > 0:
            cmds[0][-1] = os.path.splitext(temp_file)[0] + '_pre_subs.mkv'
            cmds.append(base_cmd + ['-i', cmds[0][-1], '-map', '1:v', '-map', '1:a', '-map', '0:s', '-c', 'copy'] + sub_cmd + [temp_file])
            logging.info("Subtitle command {}".format(cmds[-1]))

        print("Commands: {}".format(cmds))
        return cmds

    @MediaProcessor.exception_logger
    def SelectEncodeCommand(self, mediainfo, codec, crf, speed, options=None):
        # Build the actual encoding command
        if codec == 'hevc_nvenc' or codec == 'h264_nvenc':
            # Pick a set of sane options if no options are specified
            max_crf = str(min(int(crf) + 7, 51))
            min_crf = str(max(int(crf) - 7, 1))

            if codec == 'hevc_nvenc':
                default_options = {'profile' : 'main10', 'level' : '5.1', 'rc' : 'vbr_hq', 'qmin' : min_crf, 'qmax' : max_crf,
                                   'spatial_aq' : '1', 'temporal_aq' : '0', 'weighted_pred' : '1', 'rc-lookahead' : '32',
                                   'bitrate' : '0'}
            else:
                default_options = {'profile' : 'high', 'level' : '4.2', 'rc' : 'vbr_hq', 'qmin' : min_crf, 'qmax' : max_crf,
                                   'spatial_aq' : '1','temporal_aq' : '0', 'weighted_pred' : '1', 'rc-lookahead' : '32',
                                   'bitrate' : '0', 'coder' : 'default', 'b_ref_mode' : 'disabled'}

            if options:
                # Override the defaults
                default_options.update(options)

            encode_cmd = ['-c:v', codec, '-preset', speed, '-profile:v', default_options['profile'], '-level', default_options['level'], '-rc', default_options['rc']]

            # Process the options and construct the FFMPEG commands
            if default_options['rc'] == 'vbr_hq':
                encode_cmd.extend(['-qmin', default_options['qmin'], '-qmax', default_options['qmax'], '-cq', crf, '-b:v', default_options['bitrate']])
            else:
                encode_cmd.extend(['-qp', crf])
            if default_options['spatial_aq'] != '0':
                encode_cmd.extend(['-spatial_aq', default_options['spatial_aq']])
            if default_options['temporal_aq'] != '0':
                encode_cmd.extend(['-temporal_aq', default_options['temporal_aq']])
            if default_options['weighted_pred'] != '0':
                encode_cmd.extend(['-weighted_pred', default_options['weighted_pred']])
            if default_options['rc-lookahead'] != '0':
                encode_cmd.extend(['-rc-lookahead', default_options['rc-lookahead']])

            if codec == 'h264_nvenc':
                if default_options['coder'] != 'default':
                    encode_cmd.extend(['-coder', default_options['coder']])
                if default_options['b_ref_mode'] != 'disabled':
                    encode_cmd.extend(['-b_ref_mode', default_options['b_ref_mode']])

        elif codec == 'x265' or codec == 'x264':
            encode_cmd = ['-c:v', 'lib' + codec, '-preset', speed, '-crf', crf]
            if 'tune' in options:
                encode_cmd.extend(['-tune', options['tune']])

        elif codec == 'vp9':
            encode_cmd = ['-c:v', 'libvpx-vp9', '-threads', '12', '-deadline', 'good', '-cpu-used', '1', '-crf', crf, '-b:v', '0'] # '-row-mt', '1'
            logging.info("Currently ignoring the speed parameter for VP9 - using 'Good', and -cpu-used 1")

        else:
            encode_cmd = ['-c:v', 'copy']

        return encode_cmd

    @MediaProcessor.exception_logger
    def SelectDecodeCommand(self, mediainfo, codec, options=None):
        if not self.config.NVDEC_SUPPORT or (options and options.get('disable_hw_decode', False)):
            logging.info("Using standard software decoding because HW Acceleration is disabled.")
            return ['-i']

        codec_to_decoder = {
            'AVC' : 'h264_cuvid',
            'V_MPEGH/ISO/HEVC' : 'hevc_cuvid',
            'HEVC' : 'hevc_cuvid',
            'JPEG' : 'mjpeg_cuvid',
            'MPEG-1 Video' : 'mpeg1_cuvid',
            'MPEG-2 Video' : 'mpeg2_cuvid',
            'MPEG-4 Video' : 'mpeg4_cuvid',
            'V_VC1' : 'vc1_cuvid',
            'V_VP8' : 'vp8_cuvid',
            'V_VP9' : 'vp9_cuvid'
        }

        for track in mediainfo.tracks:
            if track.track_type == "General":
                # if len(track.codecs_video) > 1:
                #     logging.info('More than one codec in this video, don\'t know what to do!')
                #     return ['i']
                try:
                    decoder = codec_to_decoder[track.codecs_video]
                except Exception, e:
                    logging.info('Couldn\'t find a decoder for the given track: %s' % e)
                break

        if 'decoder' in locals():
            logging.info('Using hardware decoder {} for this content'.format(decoder))
            return ['-hwaccel', 'cuvid', '-c:v', decoder, '-i']
        else:
            logging.info('Could not find a hardware decoder for this input')
            return ['-i']

    @MediaProcessor.exception_logger
    def AutoSelectEncParameters(self, mediainfo, options=None):
        if self.config.NVENC_SUPPORT and not (options and options.get('disable_hw_encode', False)):
            params = {'codec': 'hevc_nvenc', 'crf' : '23', 'speed' : 'hq'}
        else:
            # Default parameters
            params = {'codec': 'x265', 'crf' : '18', 'speed' : 'medium'}
            max_duration = 0
            for track in mediainfo.tracks:
                if (track.duration is not None):
                    max_duration = max(max_duration, float(track.duration) / 60000.0)

            # This is a long video,
            if(max_duration > 10500.0):
                params['codec'] = 'x264'
                params['crf'] = '21'
                params['speed'] = 'faster'

        logging.info("Auto-codec selection: codec {}, crf {}, speed {}".format(params['codec'], params['crf'], params['speed']))
        return params

    @MediaProcessor.exception_logger
    def Transcode(self, path, codec, crf, speed, options=None):
        if not os.path.isfile(path):
            logging.error('Path does not point to a file: {}'.format(path))

        logging.info('Transcode processing starting for %s' % path)

        # Get the media info object for this file
        mediainfo = MediaInfo.parse(path)

        # Handle auto-selecting parameters
        if codec == 'auto':
            params = self.AutoSelectEncParameters(mediainfo, options=options)
            codec = params['codec']
            speed = params['speed']
            crf = params['crf']

        try:
            # Full hardware transcode
            try:
                cmds = self.BuildFFMPEGCommands(path, mediainfo, codec, crf, speed, options=options)
                logging.info ('Transcoder command builder returned {} commands to run'.format(len(cmds)))
                for cmd in cmds:
                    self.Call(cmd)

            except Exception, e:
                logging.info('Full hardware transcoding failed, trying software decode, hardware encode: %s' % e)
                # Software decode, hardware transcode
                hw_dec_disabled = {'disable_hw_decode' : True}
                if options:
                    hw_dec_disabled.update(options)
                cmds = self.BuildFFMPEGCommands(path, mediainfo, codec, crf, speed, options=hw_dec_disabled)
                logging.info ('Transcoder command builder returned {} commands to run'.format(len(cmds)))
                for cmd in cmds:
                    self.Call(cmd)

            # Return the transcoded file
            temp_path = cmds[-1][-1]
            logging.info('Finished processing: {}, transcoded file: {}'.format(path, temp_path))
            return temp_path

        except Exception, e:
            self.Error('Something went wrong during transcoding: %s' % e)
            raise

class TranscodeScanner(Scanner.MediaScanner):
    def __init__(self, codec, crf, speed, interactive):
        # Call the super constructor
        super(TranscodeScanner, self).__init__([self.mpeg2_rule], self.transcode_action, interactive)

        # Save transcoding parameters
        self.codec = codec
        self.crf = crf
        self.speed = speed

        # Get the configuration file
        config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts.conf')

        # Create transcoder object
        self.transcoder = Transcoder(config_file_path)

    def transcode_action(self, path, mediainfo):
        # Transcode the file
        try:
            output_file = self.transcoder.Transcode(path, self.codec, self.crf, self.speed)
            # Safely overwrite the original file
            if self.transcoder.SafeOverwrite(path, output_file) == 0:
                # Make sure it ends with .mkv
                os.rename(path, os.path.splitext(path)[0] + '.mkv')
                # Clean up temporary files
                self.transcoder.Cleanup()
        except Exception, e:
            self.transcoder.Error('Could not transcode {}, cleaning up temp files and skipping...'.format(path))
            self.transcoder.Cleanup()

    def mpeg2_rule(self, mediainfo):
        for track in mediainfo.tracks:
            if track.track_type == "General" and track.codecs_video == 'MPEG-2 Video':
                print("Found a video with MPEG-2 encoding, will transcode")
                return True
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', action="append", default=[], help='"One or more directories to scan.')
    parser.add_argument("--interactive", action='store_true', help="Be prompted for each file that we want to comskip")
    parser.add_argument("--codec", default='auto', choices=['auto', 'x265', 'hevc_nvenc', 'x264', 'h264_nvenc', 'vp9', 'none'], help="What codec to use for the encoding")
    parser.add_argument("--crf", default='23', choices=map(str, range(0, 51)), help="What quality to use when for encoded (lower is higher quality and bigger files)")
    parser.add_argument("--speed", default='medium', choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo', 'hq'], help="Encoding speed (faster encoding is results in a less efficient representation)")
    args = parser.parse_args()

    transcoder = TranscodeScanner(args.codec, args.crf, args.speed, args.interactive)
    transcoder.scan(args.input)

    sys.exit(0)
