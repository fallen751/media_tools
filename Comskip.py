#!/usr/bin/python

import logging, os, shutil, subprocess, sys, tempfile, glob, time, uuid, argparse
import ConfigContainer, Scanner, MediaProcessor

class Comskip(MediaProcessor.MediaProcessor):
    @MediaProcessor.exception_logger
    def GenerateSegments(self, input_file):
        video_path = input_file

        logging.info('Using session ID: %s' % self.session_uuid)
        logging.info('Using temp dir: %s' % self.temp_dir)
        logging.info('Using input file: %s' % video_path)

        original_video_dir = os.path.dirname(video_path)
        video_basename = os.path.basename(video_path)
        video_name, video_ext = os.path.splitext(video_basename)

        if self.config.COPY_ORIGINAL or self.config.SAVE_ALWAYS:
            temp_video_path = os.path.join(self.temp_dir, video_basename)
            logging.info('Copying file to work on it: %s' % temp_video_path)
            shutil.copy(video_path, self.temp_dir)
        else:
            temp_video_path = video_path

        # Process with comskip.
        cmd = [self.config.COMSKIP_PATH, '--output', self.temp_dir, '--ini', self.config.COMSKIP_INI_PATH, temp_video_path]
        self.Call(cmd)

        edl_file = os.path.join(self.temp_dir, video_name + '.edl')
        logging.info('Using EDL: ' + edl_file)
        segments = []
        prev_segment_end = 0.0
        if os.path.exists(edl_file):
            with open(edl_file, 'rb') as edl:
                # EDL contains segments we need to drop, so chain those together into segments to keep.
                for segment in edl:
                    start, end, something = segment.split()
                    if float(start) == 0.0:
                        logging.info('Start of file is junk, skipping this segment...')
                    else:
                        keep_segment = [float(prev_segment_end), float(start)]
                        logging.info('Keeping segment from %s to %s...' % (keep_segment[0], keep_segment[1]))
                        segments.append(keep_segment)
                    prev_segment_end = end

        # Write the final keep segment from the end of the last commercial break to the end of the file.
        keep_segment = [float(prev_segment_end), -1]
        logging.info('Keeping segment from %s to the end of the file...' % prev_segment_end)
        segments.append(keep_segment)

        logging.info('Found {} segments that we want to keep.'.format(len(segments)))
        return temp_video_path, segments

    @MediaProcessor.exception_logger
    def ProcessSegments(self, input_file, segments):
        segment_files = []
        segment_list_file_path = os.path.join(self.temp_dir, 'segments.txt')
        video_basename = os.path.basename(input_file)
        video_name, video_ext = os.path.splitext(video_basename)
        output_path = os.path.join(self.temp_dir, video_basename)

        with open(segment_list_file_path, 'w+') as segment_list_file:
            for i, segment in enumerate(segments):
                segment_name = 'segment-%s' % i
                segment_file_name = '%s%s' % (segment_name, video_ext)
                segment_path = os.path.join(self.temp_dir, segment_file_name)

                # Check duration of segment
                if segment[1] == -1:
                    duration_args = []
                else:
                    duration_args = ['-t', str(segment[1] - segment[0])]

                # Use FFMPEG to generate a new file containing only this segment
                cmd = [self.config.FFMPEG_PATH, '-i', input_file, '-ss', str(segment[0])] + duration_args + ['-c', 'copy', segment_path]
                self.Call(cmd)

                # If the last drop segment ended at the end of the file, we will have written a zero-duration file.
                if os.path.exists(segment_path):
                    if os.path.getsize(segment_path) < 1000:
                        logging.info('Last segment ran to the end of the file, not adding bogus segment %s for concatenation.' % (i + 1))
                        continue

                    segment_files.append(segment_path)
                    segment_list_file.write('file \'{}\'\n'.format(segment_path))

        logging.info('Going to concatenate files from the segment list.')

        # Build concatenation part of the command
        cmd = [self.config.FFMPEG_PATH, '-y', '-f', 'concat', '-safe', '0', '-i', segment_list_file_path, '-c', 'copy', output_path]
        self.Call(cmd)
        return output_path

class ComskipScanner(Scanner.MediaScanner):
    def __init__(self, interactive):
        # Call the super constructor
        super(ComskipScanner, self).__init__([self.mpeg2_rule], self.comskip_action, interactive)

        # Process the configuration file
        config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts.conf')

        # Create PlexComskip Object
        self.comskip = Comskip(config_file_path)

    def comskip_action(self, path, mediainfo):
        # Get the segments that are commerical free
        intermediate_path, segments = self.comskip.GenerateSegments(path)

        # Cut the commercials out of the original file
        processed_file = self.comskip.ProcessSegments(intermediate_path, segments)

        # Check that file looks sane and then copy it over
        if self.comskip.SafeOverwrite(path, processed_file, .1, 1.0) == 0:
            # Clean up temporary files
            self.comskip.Cleanup()

    def mpeg2_rule(self, mediainfo):
        for track in mediainfo.tracks:
            if (track.track_type == "Video" and track.codec is not None and (track.codec == "MPEG-2V" or track.codec == "V_MPEG2") and \
                track.duration is not None and (((track.duration / 60000.0) % 30) < 2 or ((track.duration / 60000.0) % 30) > 28)):
                print("Track type: {}, Track codec: {}, Track Duration: {}".format(track.track_type, track.codec_id, track.duration / 60000.0))
                return True
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', action="append", default=[], help='"One or more directories to scan.')
    parser.add_argument("--interactive", action='store_true', help="Be prompted for each file that we want to comskip")
    args = parser.parse_args()

    comskip = ComskipScanner(args.interactive)
    comskip.scan(args.input)

    sys.exit(0)
