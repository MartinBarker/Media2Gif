### Media2Gif
## Convert video file(s) to gifs

# Instructions:
- Clone .env-template as .env
- Get IMDB API Key from here: https://www.themoviedb.org/settings/api
- Create a giphy account and enter your username/password: https://www.giphy.com

# Config file setup:
- Copy 'movie-template.cfg' and rename it to your movie (example: "Antz.cfg")
- Fill out the .cfg fields pointing to your movie file and other optional fields:
```

```
# Run make_gifs.py, this will make and describe gifs
- `source venv/bin/activate`
- `python make_gifs.py F1.cfg`

# Run giphy upload bot