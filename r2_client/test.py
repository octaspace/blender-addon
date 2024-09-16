from module.sync_r2_worker import SyncR2Worker


def multipart(worker: SyncR2Worker):
    data1 = "1" * 10000000
    data2 = "2" * 10000000
    print("data created")

    file_path = "this is/a test.txt"

    print("creating upload")
    data = worker.create_multipart_upload(file_path)
    upload_id = data["uploadId"]
    print(f"upload id is {upload_id}")
    parts = []

    print("uploading part 1")
    parts.append(worker.upload_multipart_part(file_path, upload_id, 1, data1))
    print("uploading part 2")
    parts.append(worker.upload_multipart_part(file_path, upload_id, 2, data2))

    print("completing upload")
    worker.complete_multipart_upload(file_path, upload_id, parts)
    print("getting data")
    data = worker.get_object(file_path)
    print(data[:100], data[-100:])


def single(worker: SyncR2Worker):
    data = "1" * 100 + "2" * 100

    worker.upload_single_part("this is/single test.txt", data)
    print("done")


if __name__ == '__main__':
    octa_api_token = "set yourself"
    worker = SyncR2Worker(octa_api_token)
    #multipart(worker)
    single(worker)
