#!/usr/bin/python
import logging, os, shutil, subprocess, sys, tempfile, uuid, argparse, glob, time, functools, shlex
import ConfigContainer
from logging.handlers import RotatingFileHandler

def exception_logger(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception, e:
            # Check to see if this is an instance of the MediaProcessor class
            if isinstance(args[0], MediaProcessor) and 'logged' not in vars(e):
                e.logged = True
                # Log the the exception
                logging.error("[Exception] There was an exception executing {}".format(function.__name__))
                logging.error("[Exception] {}".format(e))

                self = args[0]
                # See if we should keep the temporary files for debug
                self.keep_temp = self.keep_temp or self.config.SAVE_FORENSICS
            # re-raise the exception
            raise

    return wrapper

class MediaProcessor(object):
    def __init__(self, config_file):

        # Process the configuration file
        self.config = ConfigContainer.ConfigContainer(config_file)

        # Logging.
        self.session_uuid = str(uuid.uuid4())

        formatter = logging.Formatter('%%(asctime)-15s [MediaProcessor: %s] %%(message)s' % self.session_uuid[:6])

        handler = RotatingFileHandler(self.config.LOG_FILE_PATH, mode='a', maxBytes=8 * 1024 * 1024, backupCount=2)
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)

        logger = logging.getLogger('')
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        if self.config.CONSOLE_LOGGING:
            if len(logger.handlers) < 2:
                console = logging.StreamHandler()
                console.setLevel(logging.INFO)
                formatter = logging.Formatter('%(message)s')
                console.setFormatter(formatter)
                logger.addHandler(console)

        # If we're in a git repo, let's see if we can report our sha.
        logging.info('Script was invoked from %s' % os.getcwd())
        try:
            git_sha = subprocess.check_output('git rev-parse --short HEAD', shell=True)
            if git_sha:
                logging.info('Using version: %s' % git_sha.strip())
        except: pass

        # Create temp directory to use when processing files
        self.temp_dir = os.path.join(self.config.TEMP_ROOT, self.session_uuid)
        os.makedirs(self.temp_dir)
        self.keep_temp = False

    def __del__(self):
        if self.keep_temp or self.config.SAVE_ALWAYS:
            logging.info("keep_temp or self.config.SAVE_ALWAYS set for this temp dir: {}".format(self.temp_dir))
        else:
            logging.info("Removing temp dir: {}".format(self.temp_dir))
            shutil.rmtree(self.temp_dir)

    @exception_logger
    def MKClean(self, path, output_path):
        logging.info('Running MKClean to remux and copy')
        cmd = [self.config.MKCLEAN_PATH, '--remux', path, output_path]
        logging.info ('[mkclean] Command %s' % " ".join(cmd))
        self.Call(cmd)
        logging.info('Finished running MKClean')

    @exception_logger
    def SafeOverwrite(self, original_file, processed_file, lower_bound=.2, upper_bound=1.2, remux=True):
        logging.info('Starting safe overwrite, original file: {}, processed file: {}'.format(original_file, processed_file))
        input_size = os.path.getsize(original_file)
        output_size = os.path.getsize(processed_file)
        lower_bound = float(lower_bound) * input_size
        upper_bound = float(upper_bound) * input_size
        logging.info('Original video size: {}, Processed video size: {}'.format(self.SizeOfFormat(input_size), self.SizeOfFormat(output_size)))
        logging.info('Lower bound on safe size: {}, Upper bound on safe size: {}'.format(self.SizeOfFormat(lower_bound), self.SizeOfFormat(upper_bound)))

        if upper_bound >= output_size and output_size >= lower_bound:
            logging.info('Processed size falls within bounds, copying the output file into place: {} -> {}'.format(processed_file, original_file))
            if remux and os.path.splitext(processed_file)[1] == '.mkv':
                self.MKClean(processed_file, original_file)
            else:
                shutil.copy(processed_file, original_file)
            logging.info("Finished safe overwrite")
            return 0
        else:
            self.Error('Output file size looked wonky (too big or too small); we won\'t replace the original')
            return 1

    @exception_logger
    def Call(self, cmd):
        # def shellquote(s):
        #         return "'" + s.replace("'", "'\\''") + "'"

        # logging.info("[Command] {}".format(" ".join(cmd)))
        # stringified_cmd = ""
        # for item in cmd:
        #     if os.access(os.path.split(item)[0], os.F_OK):
        #         #item = shlex.quote(item)
        #         item = shellquote(item)
        #     stringified_cmd += item + " "

        # logging.info("[Command] Escaped version:  {}".format(stringified_cmd))

        logging.info("[Command] {}".format(" ".join(cmd)))
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT) #, shell=True)
        except Exception, e:
            logging.error(e.output)
            logging.info("[Command] return code: {}".format(e.returncode))
            raise

        logging.info('[Command] Completed Successfully')

    # Clean up after ourselves and exit.
    @exception_logger
    def Cleanup(self):
        files = glob.glob(os.path.join(self.temp_dir, '*'))
        logging.info('Removing these temp files: {}'.format(files))
        for f in files:
            os.remove(f)

    @exception_logger
    def Error(self, message):
        logging.error(message)
        # See if we should keep the temporary files for debug
        self.keep_temp = self.keep_temp or self.config.SAVE_FORENSICS

    @exception_logger
    # Human-readable bytes.
    def SizeOfFormat(self, num, suffix='B'):
        for unit in ['','K','M','G','T','P','E','Z']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Y', suffix)
