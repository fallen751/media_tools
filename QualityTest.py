#!/usr/bin/python

import os, shutil, subprocess, sys, argparse, time, collections, datetime
import Comskip, Transcoder, MediaProcessor
from pymediainfo import MediaInfo

class QualityTester(MediaProcessor.MediaProcessor):
    def __init__(self, input_file, output_dir):
        # Process the configuration file
        config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts.conf')

        # Call the super constructor
        super(QualityTester, self).__init__(config_file_path)

        # Handle our input and output files
        self.input_path = os.path.abspath(input_file)
        self.input_basename = os.path.splitext(os.path.basename(self.input_path))[0]
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        elif not os.path.isdir(output_dir):
            raise Exception("Output path is not a directory")
        self.output_dir = output_dir

        # Create result type
        self.ResultType = collections.namedtuple('QualTestResult', ['name', 'encode_time', 'bitrate', 'file_size'])

        # Create transcoder
        self.transcoder = Transcoder.Transcoder(config_file_path)

        return

    def CreateTestName(self, codec, crf, preset, options):
        output_name = self.input_basename + "_{}_{}_{}_crf_{}".format(codec, preset, options.get('rc', 'vbr_hq'), crf)
        if options.get('spatial_aq', '1') != '0':
            output_name += "_{}".format("spatial_aq")
        if options.get('temporal_aq', '0') != '0':
            output_name += "_{}".format("temporal_aq")
        if options.get('weighted_pred', '1') != '0':
            output_name += "_{}".format("weighted_pred")
        if options.get('rc-lookahead', '32') != '0':
            output_name += "_{}_{}".format("rc-lookahead", options.get('rc-lookahead', '32'))
        if 'qmin' in options:
            output_name += "_qmin_{}".format(options['qmin'])
        if 'qmax' in options:
            output_name += "_qmax_{}".format(options['qmax'])
        if 'pix_fmt' in options:
            output_name += "_pix_fmt_{}".format(options['pix_fmt'])

        return output_name

    def IssueTest(self, codec, crf, preset, options):
        # Get the name for this test
        test_name = self.CreateTestName(codec, crf, preset, options)

        # Create the subdirectory to hold these test results
        test_output_dir = os.path.join(self.output_dir, test_name)
        if not os.path.isdir(test_output_dir):
            os.makedirs(test_output_dir)

        # Time and transcode the file
        start_time = time.time()
        transcoded_file = self.transcoder.Transcode(self.input_path, codec, crf, preset, options=options)
        end_time = time.time()

        # Move the file to the output directory
        file_output_path = os.path.join(test_output_dir, test_name + ".mkv")
        print("Copying transcode file to: {}".format(file_output_path))
        shutil.move(transcoded_file, file_output_path)

        # Output individual video frames
        print("Generating still images from encode")
        image_cmd = [self.config.FFMPEG_PATH, '-y', '-i', file_output_path, '-vf', 'fps=1/60', os.path.join(test_output_dir, r'frame_%03d.png')]
        self.Call(image_cmd)

        # Record metadata information
        bitrate = '0'
        size = '0'
        mediainfo = MediaInfo.parse(file_output_path)
        for track in mediainfo.tracks:
            if track.track_type == "General":
               size = self.SizeOfFormat(int(track.file_size))
               bitrate = track.other_overall_bit_rate[0]
        delta = datetime.timedelta(seconds=(end_time - start_time))

        # Add the result record to the list
        self.results.append(self.ResultType(test_name, str(delta), bitrate, size))

    def TestNvencH265(self, time_options):
        options = {'rc' : 'vbr_hq', 'spatial_aq' : '0', 'temporal_aq' : '0', 'weighted_pred' : '0', 'rc-lookahead' : '0'}
        options.update(time_options)

        # Preset settings
        for preset in ['slow', 'medium', 'fast', 'hq', 'lossless']:
            self.IssueTest('hevc_nvenc', '23', preset, options)

        # Constant CRF/QP tests
        for m in ['vbr_hq', 'constqp']:
            options['rc'] = m

            self.IssueTest('hevc_nvenc', '23', 'hq', options)

            options['spatial_aq'] = '1'
            self.IssueTest('hevc_nvenc', '23', 'hq', options)
            options['spatial_aq'] = '0'

            options['weighted_pred'] = '1'
            self.IssueTest('hevc_nvenc', '23', 'hq', options)
            options['weighted_pred'] = '0'

            options['rc-lookahead'] = '32'
            self.IssueTest('hevc_nvenc', '23', 'hq', options)
            options['rc-lookahead'] = '0'

            # All options together
            options['spatial_aq'] = '1'
            options['weighted_pred'] = '1'
            options['rc-lookahead'] = '32'
            self.IssueTest('hevc_nvenc', '23', 'hq', options)
            options['spatial_aq'] = '0'
            options['weighted_pred'] = '0'
            options['rc-lookahead'] = '0'

        # Use these as the default options for the rest of our testing
        options['spatial_aq'] = '1'
        options['weighted_pred'] = '1'
        options['rc-lookahead'] = '32'

        # Pixel formats
        for pf in ['yuv420p', 'nv12', 'yuv444p']:
            options['pix_fmt'] = pf
            self.IssueTest('hevc_nvenc', '23', 'hq', options)
        option.pop('pix_fmt')

        # Various CRF/QP settings
        for crf in map(str, range(16, 28)):
            options['rc'] = 'vbr_hq'
            self.IssueTest('hevc_nvenc', crf, 'hq', options)

            options['rc'] = 'constqp'
            self.IssueTest('hevc_nvenc', crf, 'hq', options)

        # Specific VBR HQ testing
        options['rc'] = 'vbr_hq'
        for qwin in [12, 9, 6, 3, 1]:
            options['qmin'] = str(23 - qwin)
            options['qmax'] = str(23 + qwin)
            self.IssueTest('hevc_nvenc', '23', 'hq', options)

    def TestNvencH264(self, time_options):
        options = {'rc' : 'vbr_hq', 'spatial_aq' : '0', 'temporal_aq' : '0', 'weighted_pred' : '0', 'rc-lookahead' : '0'}
        options.update(time_options)

        # Preset settings
        for preset in ['slow', 'medium', 'fast', 'hq', 'lossless']:
            self.IssueTest('nvenc_h264', '23', preset, options)

        # Constant CRF/QP tests
        for m in ['vbr_hq', 'constqp']:
            options['rc'] = m

            self.IssueTest('nvenc_h264', '23', 'hq', options)

            options['spatial_aq'] = '1'
            self.IssueTest('nvenc_h264', '23', 'hq', options)
            options['spatial_aq'] = '0'

            options['temporal_aq'] = '1'
            self.IssueTest('nvenc_h264', '23', 'hq', options)
            options['temporal_aq'] = '0'

            options['weighted_pred'] = '1'
            self.IssueTest('nvenc_h264', '23', 'hq', options)
            options['weighted_pred'] = '0'

            options['rc-lookahead'] = '32'
            self.IssueTest('nvenc_h264', '23', 'hq', options)
            options['rc-lookahead'] = '0'

            # All options together
            options['spatial_aq'] = '1'
            options['weighted_pred'] = '1'
            options['rc-lookahead'] = '32'
            self.IssueTest('nvenc_h264', '23', 'hq', options)
            options['spatial_aq'] = '0'
            options['weighted_pred'] = '0'
            options['rc-lookahead'] = '0'

        # Use these as the default options for the rest of our testing
        options['spatial_aq'] = '1'
        options['temporal_aq'] = '1'
        options['weighted_pred'] = '1'
        options['rc-lookahead'] = '32'

        # Pixel formats
        for pf in ['yuv420p', 'nv12', 'yuv444p']:
            options['pix_fmt'] = pf
            self.IssueTest('nvenc_h264', '23', 'hq', options)
        option.pop('pix_fmt')

        return

        # Various CRF/QP settings
        for crf in map(str, range(16, 28)):
            options['rc'] = 'vbr_hq'
            self.IssueTest('nvenc_h264', crf, 'hq', options)

            options['rc'] = 'constqp'
            self.IssueTest('nvenc_h264', crf, 'hq', options)

        # Specific VBR HQ testing
        options['rc'] = 'vbr_hq'
        for qwin in [12, 9, 6, 3, 1]:
            options['qmin'] = str(23 - qwin)
            options['qmax'] = str(23 + qwin)
            self.IssueTest('nvenc_h264', '23', 'hq', options)
        return

    def TestX265(self, time_options):
        options = {'rc' : 'crf'}
        options.update(time_options)

        # Preset settings
        for preset in ['slow', 'medium', 'fast', 'veryfast', 'superfast']:
            self.IssueTest('x265', '23', preset, options)

        # Various CRF/QP settings
        for crf in map(str, range(19, 25)):
            self.IssueTest('x265', crf, 'medium', options)

        # Pixel Format settings
        for pf in ['yuv422p', 'yuv444p']:
            options['pix_fmt'] = pf
            self.IssueTest('x264', '23', 'medium', options)

        return

    def TestX264(self, time_options):
        options = {'rc' : 'crf'}
        options.update(time_options)

        # Preset settings
        for preset in ['slow', 'medium', 'fast', 'veryfast', 'superfast']:
            self.IssueTest('x264', '23', preset, options)

        # Various CRF/QP settings
        for crf in map(str, range(19, 25)):
            self.IssueTest('x264', crf, 'medium', options)

        # Pixel Format settings
        for pf in ['yuv422p', 'yuv444p']:
            options['pix_fmt'] = pf
            self.IssueTest('x264', '23', 'medium', options)

        return

    def Test(self):
        self.results = []
        time_options = {'start_timestamp': '180', 'duration' : '300'}
        options = {'rc' : 'copy', 'spatial_aq' : '0', 'temporal_aq' : '0', 'weighted_pred' : '0', 'rc-lookahead' : '0'}
        options.update(time_options)
        self.IssueTest('copy', '22', 'medium', options)

        self.TestX264(time_options)
        self.TestX265(time_options)
        self.TestNvencH264(time_options)
        self.TestNvencH265(time_options)

        with open(os.path.join(self.output_dir, "results.txt"), 'w') as f:
            for result in self.results:
                f.write("File: {}, encode time: {}, bitrate: {}, file size: {}\n".format(result.name, result.encode_time, result.bitrate, result.file_size))

        print "{}".format(self.results)
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input_file", required = True, help="File to process")
    parser.add_argument("-o", "--output_dir", required = True, help="Directory to store results")
    args = parser.parse_args()
    qt = QualityTester(args.input_file, args.output_dir)
    qt.Test()
    sys.exit(0)
