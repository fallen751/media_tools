import argparse, os, shutil, subprocess, sys
import Scanner, MediaProcessor
from pymediainfo import MediaInfo

class RenameScanner(Scanner.MediaScanner):
    def __init__(self, interactive):
        # Call the super constructor
        super(RenameScanner, self).__init__([self.matroska_rule], self.rename_action, interactive)

    def rename_action(self, path, mediainfo):
        # Rename the file
        in_abs_path = os.path.abspath(path)
        out_abs_path = os.path.splitext(in_abs_path)[0] + ".mkv"
        try:
            print('Renaming {} to {}'.format(in_abs_path, out_abs_path))
            shutil.move(in_abs_path, out_abs_path)
        except Exception, e:
            print('Could not rename {} to {}, skipping...'.format(in_abs_path, out_abs_path))

    def matroska_rule(self, mediainfo):
        for track in mediainfo.tracks:
            if track.track_type == "General" and track.codec == 'Matroska' and track.file_extension != "mkv":
                print("Found a Matroska video that does not have the right extension")
                return True
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', action="append", default=[], help='"One or more directories to scan.')
    parser.add_argument("--interactive", action='store_true', help="Be prompted for each file that we want to comskip")
    args = parser.parse_args()

    renamer = RenameScanner(args.interactive)
    renamer.scan(args.input)

    sys.exit(0)
