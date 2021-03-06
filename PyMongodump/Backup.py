import datetime
import calendar
import pymongo
from PyMongodump import Mongotools, Mongodump, Utilities
import argparse
import itertools
import os, shutil, sys
import logging

class EmptyCollectionError(ValueError):
    pass

def iterate_months((year0,month0), (year1, month1)):
    months_to_iterate = (year1 - year0) * 12 + month1 - month0 + 1
    year,month = year0,month0
    for count in xrange(0,months_to_iterate):
        month = (month0 + count) % 12 + 1
        year  = year0  + (month0 + count) // 12
        yield (month, year)


class BackupInicial:
    def __init__(self, host = 'localhost', db = 'tmp', col = 'tmp', port = 27017, startTimeObject=None):
        self.connection = pymongo.Connection(host = host, port = port)
        self.col = self.connection[db][col]
        num_objects_to_backup = self.col.count()
        if num_objects_to_backup > 0:
            if startTimeObject:
                self.first_date = startTimeObject
            else:
                self.first_date = Mongotools.TimeObject(list(self.col.find().sort("timestamp", pymongo.ASCENDING).limit(1))[0]["timestamp"])
            self.last_date  = Mongotools.TimeObject(list(self.col.find().sort("timestamp", pymongo.DESCENDING).limit(1))[0]["timestamp"])
        else:
            raise EmptyCollectionError("This collection is empty")
        self.date_operations = BackupHelper(self.first_date, self.last_date)

    def iterate_queries(self):
        return self.date_operations.iterate_queries()

    def iterate_months(self):
        return self.date_operations.iterate_months()

    def tar_dump_directory(self, dirname, archname):
        pathtoorig = os.path.join(os.getcwd(), "dump")
        pathtodest = dirname + archname
        shutil.make_archive(pathtodest, "gztar", pathtoorig)
        #cmd = ['tar','cvzf', '%s.tgz'%(fname,), './dump']
        #subprocess.check_output(cmd)



class BackupHelper:
        def __init__(self, tobj_initial, tobj_final):
            self.tobj_initial = tobj_initial
            self.tobj_final   = tobj_final

        def iterate_months(self):
            year0, month0 = self.tobj_initial.get_yearmonth()
            year1, month1 = self.tobj_final.get_yearmonth()
            months_to_iterate = (year1 - year0) * 12 + month1 - month0 + 1
            year,month = year0,month0
            for count in xrange(0,months_to_iterate):
                month = (month0 + count-1) % 12 + 1
                year  = year0  + (month0 + count - 1) // 12
                yield (year,month)

        def iterate_monthly_date_ranges(self):
            tz = self.tobj_initial.tzinfo
            for (year,month) in self.iterate_months():
                _,end_day = calendar.monthrange(year,month)
                start_month = datetime.datetime(year, month, 1, 00,00,00,0, tzinfo = tz)
                end_month = datetime.datetime(year, month, end_day,23,59,59,999999, tzinfo = tz)
                yield (start_month, end_month)

        def iterate_timestamp_ranges(self):
           for (date0, date1) in self.iterate_monthly_date_ranges():
               tst0 = Mongotools.TimeObject(date0).get_mongotimestamp()
               tst1 = Mongotools.TimeObject(date1).get_mongotimestamp()
               yield (tst0, tst1)

        def iterate_queries(self):
            for (tst0, tst1) in self.iterate_timestamp_ranges():
                yield '{"timestamp" : {"$gte" : %d, "$lte" : %d}}'%(tst0,tst1)



class BackupScript:
    def __init__(self, host = "localhost", db = "tmp", col = "tmp", logpath = "backup.log", startMonth = None, **kwargs):# backupper = None, dumper = None):
        self.host = host
        self.db   = db
        self.col  = col
        self.logpath = logpath
        self.logger  = logging.getLogger('backup_log')
        self.startMonth = startMonth
        self.initialize_logger()
        if 'backupper' in kwargs:
            self.set_backupper(backupper = kwargs['backupper'])
        else:
            startTimeObject = self.get_startTimeObject()
            self.set_backupper(startTimeObject=startTimeObject)
        if 'dumper' in kwargs:
            self.set_dumper(dumper = kwargs['dumper'])
        else:
            self.set_dumper()

    def set_backupper(self, **kwargs):
        if 'backupper' in kwargs:
            self.backup = kwargs['backupper']
        else:
            try:
                startTimeObject = kwargs['startTimeObject']
                self.backup = BackupInicial(host = self.host, db = self.db, col = self.col, startTimeObject=startTimeObject)
            except:
                self.logger.error("This collection is empty. Try again with a non-empty collection.")
                print "This collection is empty. Try again with a non-empty collection"
                sys.exit(1)

    def get_startTimeObject(self):
        if self.startMonth:
            month = int(self.startMonth[0:2])
            year  = int(self.startMonth[2:])
            timezone_utc = Utilities.tz.tzutc()
            startDatetime = datetime.datetime(day = 01, month = month, year = year, tzinfo=timezone_utc)
        else:
            startDatetime = None
        return Mongotools.TimeObject(startDatetime)

    def iterate_backupper_months(self):
        return self.backup.iterate_months()

    def set_dumper(self, **kwargs):
        if 'dumper' in kwargs:
            self.dumper = kwargs['dumper']
        else:
            self.dumper = Mongodump.Mongodump(host = self.host, db = self.db, collections = [self.col])

    def create_backup_dir(self):
        self.backup_dir = os.getcwd() + '/backup/%s/%s/'%(self.db, self.col)
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def initialize_logger(self):
        fhandler  = logging.FileHandler(self.logpath)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fhandler.setFormatter(formatter)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(fhandler)
        self.logger.info("========================================")
        self.logger.info("==== NOVO BACKUP INICIADO ==============")
        self.logger.info("==== %s ========                        "%(datetime.datetime.now(),))
        self.logger.info("========================================")

    def logtarlist(self):
        tarlist = sorted(os.listdir(self.backup_dir))
        for bkfile in tarlist:
            self.logger.info("\t file created: %s"%(bkfile))

    def do_backup(self):
        self.create_backup_dir()
        for query, (year, month) in itertools.izip(self.backup.iterate_queries(), self.backup.iterate_months()):
            self.logger.info("Dumping month: %s/%s ..."%(month, year))
            self.dumper.set_query(query)
            self.dumper.run()
            tarfilename = "%s%s%04s%02d"%(self.db, self.col, year, month)
            self.logger.info("creating tarball on %s%s.tar.gz ..."%(self.backup_dir,tarfilename))
            self.backup.tar_dump_directory(self.backup_dir, tarfilename)
            self.logger.info("OK!")
        self.logtarlist()

def backupCommandLine():
    parser = argparse.ArgumentParser(prog = "backup88", description = "Backup mongodb")
    parser.add_argument('--host', default = "localhost", const = "localhost", type = str, nargs = '?', required = True)
    parser.add_argument('--db', type = str, nargs = '?', required = True)
    parser.add_argument('--collection', type = str, nargs = '?', required = True)
    parser.add_argument('--logpath', type = str, nargs = '?', default = "backup.log")
    parser.add_argument('--startMonth', type=str, default=None, nargs='?', required = False)
    args = parser.parse_args()
    script = BackupScript(host=args.host, db=args.db, col=args.collection, logpath=args.logpath, startMonth=args.startMonth)
    script.do_backup()
