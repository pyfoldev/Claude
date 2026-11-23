import path from 'node:path';
const M = {
  '.txt': 'text/plain', '.md': 'text/markdown', '.json': 'application/json', '.html': 'text/html', '.css': 'text/css',
  '.js': 'text/javascript', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.svg': 'image/svg+xml', '.pdf': 'application/pdf', '.zip': 'application/zip',
  '.apk': 'application/vnd.android.package-archive', '.aab': 'application/octet-stream', '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav', '.m4a': 'audio/mp4', '.ogg': 'audio/ogg', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.csv': 'text/csv', '.xml': 'application/xml', '.log': 'text/plain',
};
export default (name) => M[path.extname(name).toLowerCase()] || 'application/octet-stream';
