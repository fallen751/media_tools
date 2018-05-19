import ConfigParser, os, tempfile

class ConfigContainer(object):
    def __init__(self, path):

        if not os.path.exists(path):
            print('Config file not found: %s' % path)
            print('Make sure scripts.conf is placed in the same directory as this script.')
            raise IOError("File does not exist: {}".format(path))

        config = ConfigParser.SafeConfigParser({'comskip-ini-path' : os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comskip.ini'), 'temp-root' : tempfile.gettempdir()})
        config.read(path)

        self.COMSKIP_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-path')))
        self.COMSKIP_INI_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-ini-path')))
        self.FFMPEG_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'ffmpeg-path')))
        self.MKCLEAN_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'mkclean-path')))
        self.NVENC_SUPPORT = config.getboolean('Transcoding', 'nvenc_support')
        self.NVDEC_SUPPORT = config.getboolean('Transcoding', 'nvdec_support')
        self.LOG_FILE_PATH = os.path.expandvars(os.path.expanduser(config.get('Logging', 'logfile-path')))
        self.CONSOLE_LOGGING = config.getboolean('Logging', 'console-logging')
        self.TEMP_ROOT = os.path.expandvars(os.path.expanduser(config.get('File Manipulation', 'temp-root')))
        self.COPY_ORIGINAL = config.getboolean('File Manipulation', 'copy-original')
        self.SAVE_ALWAYS = config.getboolean('File Manipulation', 'save-always')
        self.SAVE_FORENSICS = config.getboolean('File Manipulation', 'save-forensics')
