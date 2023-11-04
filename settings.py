import secrets

FLICKR_APP_NAME = "IIIF Explorer"

REST_TEMPLATE = (f"https://www.flickr.com/services/rest/?method={{method}}&api_key={secrets.FLICKR_API_KEY}"
                 f"&format=json&nojsoncallback=1")

PHOTO_EXTRAS = ("description,license,date_upload,date_taken,owner_name,icon_server,original_format,last_update,geo,"
                "tags,machine_tags,o_dims,views,media,path_alias,"
                "url_sq,url_t,url_s,url_q,url_m,url_n,url_z,url_c,url_l, rl_o")

PROXY = True
