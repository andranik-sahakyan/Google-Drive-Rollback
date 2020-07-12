from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
import io


FOLDER = 'application/vnd.google-apps.folder'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


creds = None
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

service = build('drive', 'v3', credentials=creds)


def download_file(file, fileName):
    # FIX LARGE FILE CHUNK BUG
    fh = io.FileIO(fileName, mode='wb')
    downloader = MediaIoBaseDownload(fh, file)
    done = False
    while not done:
        status, done = downloader.next_chunk(3)


def iterfiles(name=None, is_folder=None, parent=None, order_by='folder,name,createdTime'):
    q = []
    if name is not None:
        q.append("name = '%s'" % name.replace("'", "\\'"))
    if is_folder is not None:
        q.append("mimeType %s '%s'" % ('=' if is_folder else '!=', FOLDER))
    if parent is not None:
        q.append("'%s' in parents" % parent.replace("'", "\\'"))
    params = {'pageToken': None, 'orderBy': order_by}
    if q:
        params['q'] = ' and '.join(q)
    while True:
        response = service.files().list(**params).execute()
        for f in response['files']:
            yield f
        try:
            params['pageToken'] = response['nextPageToken']
        except KeyError:
            return


def walk(top='root', by_name=False):
    if by_name:
        top, = iterfiles(name=top, is_folder=True)
    else:
        top = service.files().get(fileId=top).execute()
        if top['mimeType'] != FOLDER:
            raise ValueError('not a folder: %r' % top)
    stack = [((top['name'],), top)]
    while stack:
        path, top = stack.pop()
        dirs, files = is_file = [], []
        for f in iterfiles(parent=top['id']):
            is_file[f['mimeType'] != FOLDER].append(f)
        yield path, top, dirs, files
        if dirs:
            stack.extend((path + (d['name'],), d) for d in reversed(dirs))


def compare_dates(d1, d2):
    for d in zip(d1, d2):
        if d[0] < d[1]:
            return True


def find_revision(revisions, targetDate):
    for revision in reversed(revisions):
        modifiedDate = revision['modifiedTime'][:10].split('-')
        if compare_dates(modifiedDate, targetDate):
            return revision


def decrypt_fileName(fileName):
    index = fileName.find('.[ID]')
    if index != -1:
        return fileName[:index] 


def main():
    for path, root, dirs, files in walk():
        os.makedirs("/mnt/d/" + '/'.join(path), exist_ok=True)
        for file in files:
            print(f"{'/'.join(path)}/{file['name']}")

            # get revisions list for file
            revisions = service.revisions().list(
                fileId=file.get('id')
            ).execute().get('revisions')

            # dowlnload latest unencrypted version
            latestUnencrypted = find_revision(revisions, ['2020', '07', '05'])
            if latestUnencrypted:
                request = service.revisions().get_media(
                    fileId=file.get('id'),
                    revisionId=latestUnencrypted.get('id')
                )

                decryptedFile = decrypt_fileName(file['name'])
                savePath = f"/mnt/d/{'/'.join(path)}/{decryptedFile}"
                download_file(request, savePath)


if __name__ == '__main__':
    main()
