#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube to MP3 Converter = v2.0.0
A tool to download and convert YouTube videos to MP3 format.
"""

import re
import os
import sys
import time
import queue
import logging
import threading
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Union, Dict, Any
from argparse import ArgumentParser, RawTextHelpFormatter, ArgumentTypeError

import yt_dlp
import validators
import colorama
import requests
import inquirer
from inquirer import themes
from colorama import Fore, Style
from tqdm import tqdm
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
from mutagen.mp3 import MP3

# Initialize colorama
colorama.init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored log output"""
    
    COLORS = {
        'DEBUG': Style.BRIGHT + Fore.BLUE,
        'INFO': Style.BRIGHT + Fore.GREEN,
        'WARNING': Style.BRIGHT + Fore.YELLOW,
        'ERROR': Style.BRIGHT + Fore.RED,
        'CRITICAL': Style.BRIGHT + Fore.RED + colorama.Back.WHITE
    }

    def format(self, record):
        log_message = super().format(record)
        return f"{self.COLORS.get(record.levelname, '')}{log_message}{Style.RESET_ALL}"


class ConsoleHandler(logging.StreamHandler):
    """Custom handler that clears the line before printing"""

    def emit(self, record):
        try:
            # Clear the current line
            sys.stdout.write("\033[K")
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class Logger:
    """Handles all logging operations"""

    def __init__(self, level=logging.INFO):
        self.logger = logging.getLogger('youtube2mp3')
        self.logger.setLevel(level)

        # Clear any existing handlers
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Create console handler
        console_handler = ConsoleHandler(sys.stdout)
        console_handler.setLevel(level)

        # Create formatter
        formatter = ColoredFormatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)

        # Add handler to logger
        self.logger.addHandler(console_handler)

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)


class MetadataManager:
    """Manages metadata for MP3 files"""

    @staticmethod
    def add_metadata(mp3_file: Path, title: str, artist: str = "YouTube", album: str = "YouTube to MP3") -> None:
        """Add metadata to an MP3 file"""
        try:
            audio = MP3(mp3_file, ID3=ID3)

            # Create ID3 tag if it doesn't exist
            try:
                audio.add_tags()
            except:
                pass

            # Set the title
            audio.tags.add(TIT2(encoding=3, text=title))

            # Set the artist
            audio.tags.add(TPE1(encoding=3, text=artist))

            # Set the album
            audio.tags.add(TALB(encoding=3, text=album))

            # Save the changes
            audio.save()
            return True
        except Exception as e:
            print(f"Error adding metadata: {e}")
            return False

    @staticmethod
    def download_thumbnail(video_info: Dict[str, Any]) -> Optional[bytes]:
        """Download the video thumbnail"""
        try:
            if 'thumbnails' in video_info and video_info['thumbnails']:
                # Get the highest quality thumbnail
                thumbnail_url = video_info['thumbnails'][-1]['url']
                response = requests.get(thumbnail_url)
                if response.status_code == 200:
                    return response.content
            return None
        except Exception:
            return None

    @staticmethod
    def add_thumbnail(mp3_file: Path, thumbnail_data: bytes) -> bool:
        """Add thumbnail as album art to MP3 file"""
        try:
            audio = MP3(mp3_file, ID3=ID3)

            # Create ID3 tag if it doesn't exist
            try:
                audio.add_tags()
            except:
                pass

            # Add the album art
            audio.tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=thumbnail_data
                )
            )

            # Save the changes
            audio.save()
            return True
        except Exception as e:
            print(f"Error adding thumbnail: {e}")
            return False


class YouTubeSearcher:
    """Searches for YouTube videos"""

    @staticmethod
    def search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search for YouTube videos using yt-dlp"""
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'force_generic_extractor': True,
                'default_search': 'ytsearch',
                'max_downloads': max_results,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

                if not search_results or 'entries' not in search_results:
                    return []

                results = []
                for entry in search_results['entries']:
                    if entry:
                        results.append({
                            'id': entry.get('id', ''),
                            'title': entry.get('title', 'Unknown Title'),
                            'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                            'duration': entry.get('duration_string', 'Unknown Duration'),
                            'uploader': entry.get('uploader', 'Unknown Uploader')
                        })

                return results
        except Exception as e:
            print(f"Error searching YouTube: {e}")
            return []


class ProgressBar:
    """Custom progress bar for downloads"""

    def __init__(self, desc: str = "Downloading"):
        self.pbar = None
        self.desc = desc

    def __call__(self, d: Dict[str, Any]) -> None:
        if d['status'] == 'downloading':
            if self.pbar is None:
                try:
                    total = d.get('total_bytes')
                    if total is None:
                        total = d.get('total_bytes_estimate', 0)

                    self.pbar = tqdm(
                        total=total,
                        unit='B',
                        unit_scale=True,
                        desc=self.desc,
                        ascii=True
                    )
                except Exception:
                    pass

            if self.pbar:
                try:
                    downloaded = d.get('downloaded_bytes', 0)
                    self.pbar.update(downloaded - self.pbar.n)
                except Exception:
                    pass

        elif d['status'] == 'finished' and self.pbar:
            self.pbar.close()
            self.pbar = None


class YouTubeDownloader:
    """Handles downloading and converting YouTube videos to MP3"""

    def __init__(self, output_dir: Path, skip_playlist: bool = True, 
                logger: Optional[Logger] = None, rate_limit: Optional[int] = None,
                add_metadata: bool = True):
        self.output_dir = output_dir
        self.skip_playlist = skip_playlist
        self.logger = logger or Logger()
        self.rate_limit = rate_limit
        self.add_metadata = add_metadata

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_download_options(self) -> dict:
        """Get the options for yt-dlp"""
        options = {
            'format': 'bestaudio/best',
            'noplaylist': self.skip_playlist,
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'logger': self.logger.logger,
            'progress_hooks': [ProgressBar()],
            'writethumbnail': self.add_metadata,
            'writeinfojson': self.add_metadata,
        }

        # Add rate limit if specified
        if self.rate_limit:
            options['ratelimit'] = self.rate_limit * 1024  # Convert to bytes

        return options

    def _process_metadata(self, info_dict: Dict[str, Any], filename: str) -> None:
        """Process metadata for the downloaded file"""
        if not self.add_metadata:
            return

        try:
            # Get the base filename without extension
            base_filename = os.path.splitext(filename)[0]
            mp3_file = Path(f"{base_filename}.mp3")

            if not mp3_file.exists():
                self.logger.warning(f"MP3 file not found: {mp3_file}")
                return

            # Add basic metadata
            title = info_dict.get('title', os.path.basename(base_filename))
            artist = info_dict.get('uploader', 'YouTube')
            album = info_dict.get('album', 'YouTube to MP3')

            MetadataManager.add_metadata(mp3_file, title, artist, album)

            # Try to add thumbnail
            thumbnail_file = Path(f"{base_filename}.jpg")
            if thumbnail_file.exists():
                with open(thumbnail_file, 'rb') as f:
                    thumbnail_data = f.read()
                MetadataManager.add_thumbnail(mp3_file, thumbnail_data)
                # Clean up thumbnail file
                thumbnail_file.unlink(missing_ok=True)

            # Clean up info JSON file
            info_json = Path(f"{base_filename}.info.json")
            if info_json.exists():
                info_json.unlink(missing_ok=True)

            self.logger.info(f"Added metadata to {mp3_file.name}")

        except Exception as e:
            self.logger.error(f"Error processing metadata: {e}")

    def download(self, url: str) -> bool:
        """Download and convert a YouTube video to MP3"""
        options = self._get_download_options()

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                self.logger.info(f"Processing URL: {url}")
                info_dict = ydl.extract_info(url, download=True)

                if info_dict:
                    filename = ydl.prepare_filename(info_dict)
                    self._process_metadata(info_dict, filename)

                return True
        except yt_dlp.utils.DownloadError as error:
            self.logger.error(f"Download failed: {error}")
            return False


class ThreadedDownloader:
    """Handles multi-threaded downloading"""

    def __init__(self, urls: List[str], output_dir: Path, num_threads: int, 
                skip_playlist: bool = True, logger: Optional[Logger] = None,
                rate_limit: Optional[int] = None, add_metadata: bool = True):
        self.urls = urls
        self.output_dir = output_dir
        self.num_threads = num_threads
        self.skip_playlist = skip_playlist
        self.logger = logger or Logger()
        self.rate_limit = rate_limit
        self.add_metadata = add_metadata
        self.url_queue = queue.Queue()

        # Add URLs to queue
        for url in self.urls:
            self.url_queue.put(url)

    def _worker(self) -> None:
        """Worker function for threaded downloads"""
        downloader = YouTubeDownloader(
            output_dir=self.output_dir,
            skip_playlist=self.skip_playlist,
            logger=self.logger,
            rate_limit=self.rate_limit,
            add_metadata=self.add_metadata
        )

        while not self.url_queue.empty():
            url = self.url_queue.get()
            downloader.download(url)
            self.url_queue.task_done()

    def start(self) -> None:
        """Start the threaded download process"""
        self.logger.info(f"Starting {self.num_threads} download threads")

        threads = []
        for i in range(self.num_threads):
            thread = threading.Thread(target=self._worker)
            thread.daemon = True
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        self.logger.info("All downloads completed")


class URLExtractor:
    """Extracts YouTube URLs from a file"""
    
    @staticmethod
    def extract_from_file(file_path: Path) -> Set[str]:
        """Extract YouTube URLs from a file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # URL pattern regexp
        url_pattern = re.compile(
            r"(http|https)://([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])?"
        )
        
        # Detect YouTube URLs
        matches = re.finditer(url_pattern, content)
        return {url.group() for url in matches if 'youtu' in url.group()}


class ArgumentValidator:
    """Validates command line arguments"""
    
    @staticmethod
    def validate_url(url: str) -> str:
        """Validate a YouTube URL"""
        if not validators.url(url):
            raise ArgumentTypeError(f"Invalid URL: {url}")
        
        if 'youtu' not in url:
            raise ArgumentTypeError(f"Not a YouTube URL: {url}")
        
        return url
    
    @staticmethod
    def validate_file(file_path: str) -> Path:
        """Validate that a file exists and is readable"""
        path = Path(file_path)
        
        if not path.is_file():
            raise ArgumentTypeError(f"File does not exist: {file_path}")
        
        if not os.access(path, os.R_OK):
            raise ArgumentTypeError(f"File is not readable: {file_path}")
        
        return path
    
    @staticmethod
    def validate_directory(dir_path: str) -> Path:
        """Validate that a directory exists and is writable"""
        path = Path(dir_path)
        
        if not path.is_dir():
            raise ArgumentTypeError(f"Directory does not exist: {dir_path}")
        
        if not os.access(path, os.W_OK):
            raise ArgumentTypeError(f"Directory is not writable: {dir_path}")
        
        return path
    
    @staticmethod
    def validate_rate_limit(rate: str) -> int:
        """Validate rate limit (in KB/s)"""
        try:
            rate_int = int(rate)
            if rate_int <= 0:
                raise ArgumentTypeError("Rate limit must be a positive integer")
            return rate_int
        except ValueError:
            raise ArgumentTypeError("Rate limit must be a positive integer")


class YouTubeToMP3:
    """Main application class"""
    
    def __init__(self):
        self.logger = Logger()
        self.args = self._parse_arguments()
    
    def _parse_arguments(self):
        """Parse command line arguments"""
        parser = ArgumentParser(
            description=f"{Fore.RED}YouTube{Style.RESET_ALL} to {Fore.GREEN}MP3{Style.RESET_ALL} Converter",
            formatter_class=RawTextHelpFormatter
        )
        
        input_group = parser.add_mutually_exclusive_group(required=True)
        input_group.add_argument(
            '-u', '--url',
            type=ArgumentValidator.validate_url,
            help='Specify a YouTube URL',
            metavar='URL'
        )
        input_group.add_argument(
            '-f', '--file',
            type=ArgumentValidator.validate_file,
            help='Specify a file containing YouTube URLs',
            metavar='FILE'
        )
        input_group.add_argument(
            '-s', '--search',
            help='Search for YouTube videos',
            metavar='QUERY'
        )
        
        parser.add_argument(
            '-t', '--threads',
            type=int,
            help='Number of download threads to use',
            default=1,
            metavar='N'
        )
        
        parser.add_argument(
            '-p', '--playlist',
            action='store_true',
            help='Download playlists (default: skip playlists)'
        )
        
        parser.add_argument(
            '-o', '--output',
            type=ArgumentValidator.validate_directory,
            help='Output directory for downloaded files',
            metavar='DIR'
        )
        
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '-r', '--rate-limit',
            type=ArgumentValidator.validate_rate_limit,
            help='Limit download rate (KB/s)',
            metavar='RATE'
        )
        
        parser.add_argument(
            '-n', '--no-metadata',
            action='store_true',
            help='Skip adding metadata to MP3 files'
        )
        
        parser.add_argument(
            '--search-results',
            type=int,
            default=5,
            help='Number of search results to display',
            metavar='N'
        )
        
        return parser.parse_args()
    
    def _get_output_directory(self) -> Path:
        """Get the output directory"""
        if self.args.output:
            return self.args.output
        
        # Create a timestamped directory
        dir_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = Path(dir_name)
        path.mkdir(exist_ok=True)
        return path
    
    def _handle_search(self) -> Optional[str]:
        """Handle search functionality with interactive selection"""
        self.logger.info(f"Searching for: {self.args.search}")
        results = YouTubeSearcher.search(self.args.search, self.args.search_results)
        
        if not results:
            self.logger.error("No search results found")
            return None
        
        # Display search results header
        print("\n" + "=" * 80)
        print(f"{Fore.CYAN}Search Results for: {Fore.WHITE}{self.args.search}{Style.RESET_ALL}")
        print("=" * 80)

        choices = []
        for i, result in enumerate(results, 1):
            title = result['title']
            duration = result['duration']
            uploader = result['uploader']
            display = f"{title} ({duration}) by {uploader}"
            choices.append((display, result['url']))

        choices.append(("Quit", None))

        questions = [
            inquirer.List(
                'url',
                message="Select a video to download",
                choices=choices,
                carousel=True
            ),
        ]

        theme = themes.GreenPassion()

        try:
            answers = inquirer.prompt(questions, theme=theme)
            return answers['url'] if answers else None
        except Exception as e:
            self.logger.error(f"Selection error: {e}")
            return None

    def run(self) -> None:
        """Run the application"""
        # Set logger level based on verbose flag
        if self.args.verbose:
            self.logger = Logger(level=logging.DEBUG)

        # Get output directory
        output_dir = self._get_output_directory()
        self.logger.info(f"Output directory: {output_dir}")

        # Process based on input type
        if self.args.search:
            url = self._handle_search()
            if url:
                self._process_url(url, output_dir)
        elif self.args.file:
            self._process_file(self.args.file, output_dir)
        else:
            self._process_url(self.args.url, output_dir)

    def _process_file(self, file_path: Path, output_dir: Path) -> None:
        """Process a file containing URLs"""
        urls = URLExtractor.extract_from_file(file_path)

        if not urls:
            self.logger.error("No YouTube URLs found in the file")
            return

        self.logger.info(f"Found {len(urls)} YouTube URLs")

        # Use threaded downloader if more than one thread requested
        if self.args.threads > 1:
            self.logger.info(f"Using {self.args.threads} download threads")
            downloader = ThreadedDownloader(
                urls=list(urls),
                output_dir=output_dir,
                num_threads=self.args.threads,
                skip_playlist=not self.args.playlist,
                logger=self.logger,
                rate_limit=self.args.rate_limit,
                add_metadata=not self.args.no_metadata
            )
            downloader.start()
        else:
            self.logger.info("Using single-threaded mode")
            downloader = YouTubeDownloader(
                output_dir=output_dir,
                skip_playlist=not self.args.playlist,
                logger=self.logger,
                rate_limit=self.args.rate_limit,
                add_metadata=not self.args.no_metadata
            )

            for url in urls:
                downloader.download(url)

    def _process_url(self, url: str, output_dir: Path) -> None:
        """Process a single URL"""
        downloader = YouTubeDownloader(
            output_dir=output_dir,
            skip_playlist=not self.args.playlist,
            logger=self.logger,
            rate_limit=self.args.rate_limit,
            add_metadata=not self.args.no_metadata
        )
        downloader.download(url)


def main():
    try:
        app = YouTubeToMP3()
        app.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Process interrupted by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
