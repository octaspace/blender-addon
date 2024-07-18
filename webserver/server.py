import sanic
from sanic import response
from backend import Sessions, Upload, Download
import time
app = sanic.Sanic("FileServer")


@app.route("/api/upload", methods=["POST", "GET"])
async def upload(request):
    if request.method == "POST":
        data = request.json
        directory = data.get("path")
        _time = int(time.time())
        Sessions.uploads[_time] = Upload(directory)
        request.app.add_task(Sessions.uploads[_time].start())
        return response.json({"session_id": Sessions.uploads[_time].session_id})
    
    elif request.method == "GET":
        return response.json({"uploads": Sessions.toJSON()['uploads']})
    
@app.route("/api/transfers", methods=["GET"])
async def upload(request):
    return response.json({"transfers": Sessions.toJSON()})
    
    
app.run(host="0.0.0.0", port=8000, single_process=True, access_log=True)
