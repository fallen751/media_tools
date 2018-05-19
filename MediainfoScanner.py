#!/usr/bin/python
import logging, pprint, argparse, sys, Scanner
from pymediainfo import MediaInfo

class MediainfoScanner(Scanner.MediaScanner):

    def __init__(self):
        # Call the super constructor
        super(MediainfoScanner, self).__init__([self.print_media_info_rule], self.no_action, False)
        self.pp = pprint.PrettyPrinter(indent = 4)

    def no_action(self, path, mediainfo):
        return

    def print_media_info_rule(self, mediainfo):
        self.pp.pprint([vars(track) for track in mediainfo.tracks])
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', action="append", default=[], help='"One or more directories to scan.')
    args = parser.parse_args()

    minfo = MediainfoScanner()
    minfo.scan(args.input)

    sys.exit(0)
