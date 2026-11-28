const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('veil', {
  state: () => ipcRenderer.invoke('state'),
  save: t => ipcRenderer.invoke('save', t),
  toggle: () => ipcRenderer.invoke('toggle')
});
