## youtube2mp3

**youtube2mp3.py**: A very simple and minimal youtube to mp3 converter using [youtube-dl](https://github.com/rg3/youtube-dl) (_Of course the script's functionality is already provided by youtube-dl_).

As input can be either a single youtube-url or a file that contains youtube-urls (*the file does not need to have a specific format*).

```
$ ./youtube2mp3.py -h
usage: youtube2mp3.py [-h] (-u  | -f ) [-p] [-o]

youtube2mp3: A simple youtube to mp3 converter using youtube-dl.

arguments:
  -h, --help      show this help message and exit
  -u , --url      Specify a youtube url
  -f , --file     Specify a file that contains youtube urls
  -p, --playlist  Specify if you want to download playlists
  -o , --output   Specify a custom download directory [optional]
```

**Requirements:**
*   [youtube-dl](https://github.com/rg3/youtube-dl#installation)
*   ffmpeg
*   [colorama](https://pypi.python.org/pypi/colorama)
*   [validators](https://pypi.python.org/pypi/validators/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details