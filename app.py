import flask
import requests
import json
from flask import Flask, request, render_template, url_for, jsonify, redirect, Response
from flask_cors import CORS
from flask_caching import Cache

import secrets
import settings
from settings import REST_TEMPLATE

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
CORS(app)
cache = Cache(app)
app.wsgi_app = ProxyFix(app.wsgi_app)

# TODO
# reverse the order of photos for user stream, latest first
# find some other thing to make manifest of - collections, sets, etc
# Make manifests from tags


@app.route('/')
def hello_world():  # put application's code here
    return render_template("index.html")


@app.route('/user/<user_disp_name>')
def get_user_id(user_disp_name):
    resp = get_api_object("flickr.urls.lookupUser", url=f"https://www.flickr.com/photos/{user_disp_name}")
    return render_template("user.html", user=resp["user"])


def make_manifest(manifest_id, canvases, label, description):
    return {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": manifest_id,
        "type": "Manifest",
        "label": [{"en": [label]}],
        "metadata": [{"label": {"en": ["Description"]}, "value": {"en": [description]}}],
        "items": canvases
    }


def make_canvases(photos):
    # TODO - use secret to get larger sizes when available; this is limited to non-authenticated API calls atm
    # We're also assuming url_l, width_l and height_l exist, and they may not.
    # This can become MUCH more robust.
    canvases = []
    for photo in photos:
        photo_id = photo["id"]
        canvas_id = url_for("canvas", photo_id=photo_id, _external=True)
        size_info = get_sizes_from_photo(photo)
        canvas_with_image = {
            "id": canvas_id,
            "type": "Canvas",
            "width": size_info["largest"]["width"],
            "height": size_info["largest"]["height"],
            "label": {"en": [photo["title"]]},
            "summary": {"en": [photo["description"]["_content"]]},
            "items": [
                {
                    "id": f"{canvas_id}/annopage",
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": f"{canvas_id}/annopage/anno",
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": size_info["largest"]["url"],
                                "type": "Image",
                                "format": "image/jpeg",
                                "service": [
                                    {
                                        "id": url_for("image_info", photo_id=photo_id, _external=True),
                                        "type": "ImageService3",
                                        "profile": "level0"
                                    }
                                ],
                                "width": size_info["largest"]["width"],
                                "height": size_info["largest"]["height"],
                            },
                            "target": canvas_id
                        }
                    ]
                }
            ]
        }
        thumb_image = size_info.get("thumb", None)
        if thumb_image is not None:
            canvas_with_image["thumbnail"] = [{
                "id": thumb_image["url"],
                "type": "Image",
                "format": "image/jpg",
                "width": thumb_image["width"],
                "height": thumb_image["height"],
            }]
        canvases.append(canvas_with_image)
    return canvases


def get_sizes_from_photo(photo):
    # Using the photo object returned in a collection of photos, rather than making any new calls
    # This is where we would want to list all possible available sizes, even secret ones.
    # for now, it's enough to get _something_ out.
    size_info = {
        "largest": None,  # the biggest one we find regardless of suffix
        "thumb": None,
        "square": None,
        "all": {}
    }
    for k, v in photo.items():
        if k.startswith("width_"):
            suffix = k.split("_")[1]
            size = {
                "width": v,
                "height": photo[f"height_{suffix}"],
                "url": photo[f"url_{suffix}"],
                "suffix": suffix
            }
            if suffix == "sq":
                # don't include the square one in the list
                size_info["square"] = size
            else:
                size_info["all"]["suffix"] = size
                # but do include the thumbnail
                if suffix == "t":
                    size_info["thumb"] = size
    size_info["largest"] = max(size_info["all"].values(), key=lambda x: x["width"])
    return size_info

@app.route('/albums/<album_id>')
def get_album(album_id):
    photos = get_api_object("flickr.photosets.getPhotos", photoset_id=album_id, extras=settings.PHOTO_EXTRAS)
    data = photos["photoset"]
    canvases = make_canvases(data["photo"])
    label = data['title']
    description = f"Album from {data['ownername']}"
    manifest_id = url_for("get_album", album_id=album_id,_external=True)
    manifest = make_manifest(manifest_id, canvases, label=label, description=description)
    return jsonify(manifest)

@app.route('/photos/<user_id>')
def get_public_photos(user_id):
    person = get_api_object("flickr.people.getInfo", user_id=user_id)["person"]
    photos = get_api_object("flickr.people.getPublicPhotos", user_id=user_id, extras=settings.PHOTO_EXTRAS)["photos"]
    # to manifest, with thumbs
    canvases = make_canvases(photos["photo"])
    nameholder = person.get("realname", None) or person.get("username")
    label = nameholder["_content"]
    descholder = person.get("description", None) or {"_content": "No description"}
    description = descholder["_content"]
    manifest_id = url_for("get_public_photos", user_id=user_id, _external=True)
    manifest = make_manifest(manifest_id, canvases, label=label, description=description)
    return jsonify(manifest)


@app.route('/photos_raw/<user_id>')
def photos_raw(user_id):
    # for debug
    photos = get_api_object("flickr.people.getPublicPhotos", user_id=user_id, extras=settings.PHOTO_EXTRAS)
    return photos


@app.route('/photo/<photo_id>')
def image_info(photo_id):
    return redirect(url_for("info_json_response", photo_id=photo_id, _external=True))


@app.route('/photo/v2/<photo_id>')
def image_info_v2(photo_id):
    return redirect(url_for("info_json_response_v2", photo_id=photo_id, _external=True))


@app.route('/photo/<photo_id>/info.json')
def info_json_response(photo_id):
    # photo = get_api_object("flickr.photos.getInfo", photo_id=photo_id)
    # The Original size may or may not be present in the sizes list
    sizes = get_non_square_sizes(photo_id)
    largest = list(sizes.values())[-1]
    info_json = {
        "@context": "http://iiif.io/api/image/3/context.json",
        "id": url_for("image_info", photo_id=photo_id, _external=True),
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": "level0",
        "width": int(largest["width"]),
        "height": int(largest["height"]),
        "sizes": []
    }
    for size in sizes.values():
        info_json["sizes"].append({
            "width": size["width"],
            "height": size["height"]
        })

    # Rights - this doesn't map to IIIF cleanly but better than nothing for now
    # Need to handle Flickr All Rights Reserved
    # license_url = get_license_url(photo["photo"].get("license", None))
    # if license_url:
    #     info_json["rights"] = license_url

    return jsonify(info_json)


@app.route('/photo/v2/<photo_id>/info.json')
def info_json_response_v2(photo_id):
    # photo = get_api_object("flickr.photos.getInfo", photo_id=photo_id)
    # The Original size may or may not be present in the sizes list
    sizes = get_non_square_sizes(photo_id)
    largest = list(sizes.values())[-1]
    info_json = {
        "@context": "http://iiif.io/api/image/2/context.json",
        "@id": url_for("image_info_v2", photo_id=photo_id, _external=True),
        "protocol": "http://iiif.io/api/image",
        "profile": ["http://iiif.io/api/image/2/level0.json"],
        "width": int(largest["width"]),
        "height": int(largest["height"]),
        "sizes": []
    }
    for size in sizes.values():
        info_json["sizes"].append({
            "width": size["width"],
            "height": size["height"]
        })

    return jsonify(info_json)


@app.route('/photo/<photo_id>/full/<wh>/0/default.jpg')
@app.route('/photo/v2/<photo_id>/full/<wh>/0/default.jpg')
def image_api_request(photo_id, wh):
    sizes = get_non_square_sizes(photo_id)
    if wh == "max":
        size = list(sizes.values())[-1]
    else:
        width = int(wh.split(',')[0])
        size = sizes.get(width, None)
    if size is not None:
        if settings.PROXY:
            r = Response(response=requests.get(size["source"]).content, status=200)
            r.headers["Content-Type"] = "image/jpg"
            return r
        else:
            return redirect(size["source"])
    flask.abort(404)


def get_api_object(method, **params):
    api_url = REST_TEMPLATE.replace("{method}", method)
    for k, v in params.items():
        api_url += f"&{k}={v}"
    resp = requests.get(api_url)
    return resp.json()


def get_non_square_sizes(photo_id):
    # might be worth memoizing by photo_id?
    # TODO - use secret to get larger sizes when available
    sizes = get_api_object("flickr.photos.getSizes", photo_id=photo_id)
    return {int(s["width"]): s for s in sizes["sizes"]["size"] if "quare" not in s["label"]}


def get_license_url(license_code):
    if not license_code:
        return None
    return get_licenses().get(str(license_code), None)


@cache.memoize()
def get_licenses():
    resp = get_api_object("flickr.photos.licenses.getInfo")
    return {str(x["id"]): x["url"] for x in resp["licenses"]["license"]}


@app.route('/canvas/<photo_id>')
def canvas(photo_id):
    flask.abort(404)


@app.route('/test')
def test():
    if secrets.FLICKR_API_KEY == "NO_KEY_SET":
        return "Hasn't picked up env var"
    return json.dumps(request.headers.to_wsgi_list())


if __name__ == '__main__':
    app.run()
