#!/usr/bin/python

import os, shutil, subprocess, sys, argparse
import Comskip, Transcoder, ConfigContainer


def process_file(path, transcode, rename_ext):

    # Process the configuration file
    config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts.conf')

    path = os.path.abspath(path)

    # Create Comskip Object
    comskip = Comskip.Comskip(config_file_path)

    # Get the segments that are commerical free
    intermediate_path, segments = comskip.GenerateSegments(path)

    # Cut the commercials out of the original file
    processed_file = comskip.ProcessSegments(intermediate_path, segments)

    if transcode:
        # Transcode into a better format
        t = Transcoder.Transcoder(config_file_path)
        # CRF and preset are thrown away when using auto
        processed_file = t.Transcode(processed_file, 'auto', '23', 'medium')

    # Use the processed file extension or not?
    if rename_ext:
        path = os.path.splitext(path)[0] + os.path.splitext(procesed_file)[1]

    # Check that file looks sane and then copy it over
    return comskip.SafeOverwrite(path, processed_file, .1, 1.2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input_file", required = True, help="File to process")
    parser.add_argument("--transcode", action='store_true', help="Transcode the media into a nicer format")
    parser.add_argument("--rename_ext", action='store_true', help="Rename the extension to match the new container")
    args = parser.parse_args()

    ret = process_file(args.input_file, args.transcode, args.rename_ext)
    sys.exit(ret)
