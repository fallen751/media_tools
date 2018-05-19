#!/usr/bin/python
import os, subprocess, sys, argparse, pprint
from pymediainfo import MediaInfo

class MediaScanner(object):
    def __init__(self, rules, action, interactive):
        self.pp = pprint.PrettyPrinter(indent=4)
        self.rules = rules
        self.action = action
        self.interactive = interactive

    def check_file(self, full_path):
            print("Scanning %s" % (full_path))
            try:
                mediainfo = MediaInfo.parse(full_path)

                for rule in self.rules:
                    if rule(mediainfo):
                        print("Matched rule for file {}".format(full_path))

                        if self.interactive:
                            skip = raw_input('Do you want to process {} [Y/N]'.format(full_path))
                            if(len(skip) == 0 or skip[0].lower() == 'n'):
                                break

                        return mediainfo

            except Exception as err:
                print("Caught exception when procesing %s, exception: %s" % (full_path, err))

            return None

    def scan(self, path_list):
        if isinstance(path_list, basestring):
            path_list = [path_list]
        elif(len(path_list) == 0):
            print("No directories specified for processing, exiting...")

        files_to_transcode = {}
        for path in path_list:
            if (os.path.isdir(path)):
                for root, dirs, files in os.walk(path):
                    for item in files:
                        name, ext = os.path.splitext(item)
                        if (ext.lstrip('.') in ['mkv', 'mp4', 'ts', 'mpeg', 'mpg', 'webm', 'avi', 'ogg']):
                            full_path = os.path.join(root, item)
                            info = self.check_file(full_path)
                            if info is not None:
                                print("Adding {} to list of files to be processed...".format(full_path))
                                files_to_transcode[full_path] = info
            else:
                full_path = os.path.abspath(path)
                info = self.check_file(full_path)
                if info is not None:
                    print("Adding {} to list of files to be processed...".format(full_path))
                    files_to_transcode[full_path] = info

        self.pp.pprint([os.path.basename(path) for path in files_to_transcode.keys()])

        for item in files_to_transcode.keys():
            print('Started processing %s' % item)
            self.action(item, files_to_transcode[item])
            print('Finished processing %s' % item)

        return 0
