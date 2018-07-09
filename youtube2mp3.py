#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import re
import os
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import time
import Queue
import threading
from datetime import datetime
from os.path import isfile, join
from argparse import ArgumentParser, RawTextHelpFormatter, ArgumentTypeError
import youtube_dl
import validators
from colorama import Fore,Back,Style

# console colors
B, RA, FR  = Style.BRIGHT, Style.RESET_ALL, Fore.RESET
G, RD, Y, R, BR  = Fore.GREEN, Fore.RED, Fore.YELLOW, Back.RED, Back.RESET

# some globals used in multithreaded mode
SONGS = Queue.Queue()
DIRCTRY = None


def console():
    """argument parser"""
    parser = ArgumentParser(description="{0}{1}you{2}{0}tube{1}2{2}{0}mp3:{2} A simple youtube to mp3 converter.".format(B,RD,RA),formatter_class=RawTextHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    parser._optionals.title = "{}arguments{}".format(B,RA)
    group.add_argument('-u', "--url", type=ValidateUrl, 
                    help='Specify a {0}{1}you{2}{0}tube{2} url'.format(B,RD,RA), metavar='')
    group.add_argument('-f', "--file", type=ValidateFile, 
                    help='Specify a file that contains {0}{1}you{2}{0}tube{2} urls'.format(B,RD,RA), metavar='')
    parser.add_argument('-t', "--threads", help="Specify how many threads to use [{0}Default:{2} {1}None{2}]".format(B,RD,RA), 
                    default=None, type=int, metavar='')
    parser.add_argument('-p', "--playlist",
                    help="Download playlists [{0}Default:{2} {1}False{2}]".format(B,RD,RA), action='store_false')
    parser.add_argument('-o', "--output", help="Specify a download directory [{}optional{}]".format(RD,RA),
                    type=checkDir, required=False, metavar='')
    args = parser.parse_args()
    return args


def ret(t=.1):
    sys.stdout.write("\033[F")
    sys.stdout.write("\033[K")
    time.sleep(t)


def mkdir():
    """makes a unique directory to store the files"""
    drctry = str(datetime.now())
    os.makedirs(drctry)
    return drctry


def checkDir(dirctry):
    if not os.path.isdir(dirctry):
        raise ArgumentTypeError('{}~~> [-] Directory does not exist'.format(RD,RA))

    if os.access(dirctry, os.R_OK):
        return dirctry
    else:
        raise ArgumentTypeError('{}~~> [-] Directory is not writable'.format(RD,RA))


def ValidateFile(file):
    """validate that the file exists and is readable"""
    if not os.path.isfile(file):
        raise ArgumentTypeError('{}~~> File does not exist{}'.format(RD,RA))
    if os.access(file, os.R_OK):
        return file
    else:
        raise ArgumentTypeError('{}~~> File is not readable{}'.format(RD,RA))


def ValidateUrl(url):
    """check if it's a youtube url"""
    try:
        if validators.url(url):
            if 'youtu' in url:
                return url
            else:
                print '\n{}[x] This is not a youtube url!{}\n'.format(R,RA)
                sys.exit(0)
        else:
            print '\n{}[x] Invalid url!{}\n'.format(R,RA)
            sys.exit(0)       
    except Exception, e:
        print e
        sys.exit(0)


def extracturls(file):
    """extract urls - avoid duplicates!"""
    with open(file, 'r') as f:
        content = f.read()

    # url-pattern regexp taken from this great stackoverflow answer: 
    # https://stackoverflow.com/questions/6038061/regular-expression-to-find-urls-within-a-string/6041965#6041965
    urlptrn = re.compile(r"(http|https)://([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])?")
    
    # detect youtube urls
    matches = re.finditer(urlptrn, content)
    return list(set([url.group() for url in matches if 'youtu' in url.group()]))


class threadedLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


class CustomLogger(object):
    def debug(self, msg):
        try:
            i,j = msg.split(']',1)
            print '{0}{2}]{1}{3}'.format(B,RA,i,j)
            ret()
        except ValueError:
            print '{0}{2}{1}'.format(B,RA,msg)
            ret()

    def warning(self, msg):
        print '{0}[Warning]{1} {2}'.format(Y,RA,msg)
        ret(1)

    def error(self, msg):
        print '{0}[Error]{1} {2}'.format(RD,RA,msg)
        ret(1)


def customhook(d):
    if d['status'] == 'finished':
        print '{0}[{1}Downloaded{2}{0}]{2} {3}'.format(B,G,RA,d['filename'])


def threadedDownload(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'outtmpl': '{}/%(title)s.%(ext)s'.format(DIRCTRY),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': threadedLogger(),
        'progress_hooks': [customhook],
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except youtube_dl.utils.DownloadError, error:
            print error


def threaded_downloadmp3():
    while not SONGS.empty():
        threadedDownload(SONGS.get())


def downloadmp3(url, dirctry, plist=True):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': plist,
        'outtmpl': '{}/%(title)s.%(ext)s'.format(dirctry),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': CustomLogger(),
        'progress_hooks': [customhook],
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except youtube_dl.utils.DownloadError, error:
            print error


if __name__ == '__main__':
    user = console()
    if user.output is None:
        dirctry = mkdir()
    else:
        dirctry = user.output
    plist = user.playlist
    if plist:
        print '\n{0}[+]{1} Download playlist: {0}OFF{1}'.format(RD,RA)
    else:
        print '\n{0}[+]{1} Download playlist: {0}ON{1}'.format(G,RA)
    try:
        if user.file:
            urls = extracturls(user.file)
            if urls:
                if user.threads:
                    print "{0}[+]{1} Threaded Mode: {0}ON{1}".format(G,RA)
                    print '{1}[+]{2} {1}{0}{2} urls detected!\n'.format(len(urls),G,RA)
                    for url in urls:
                        SONGS.put(url)
                    DIRCTRY = dirctry
                    for i in range(user.threads):
                        t = threading.Thread(target=threaded_downloadmp3)
                        t.start()
                else:
                    print "{0}[+]{1} Multi-threaded Mode: {0}OFF{1}".format(RD,RA)
                    print '{1}[+]{2} {1}{0}{2} urls detected!\n'.format(len(urls),G,RA)
                    for i,url in enumerate(urls):
                        downloadmp3(url, dirctry ,plist=plist)
            else:
                print '\n{}[!] No youtube urls detected! Exiting...{}\n'.format(R,RA)
                sys.exit(0)
        else:
            downloadmp3(user.url, dirctry ,plist=plist)
    except KeyboardInterrupt:
        print '\n{}[!] Quiting...{}\n'.format(R,RA)
        sys.exit(0)
#_EOF