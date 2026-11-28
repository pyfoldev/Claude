# Veil для macOS

1. Установите зависимости: `brew install node wireguard-tools`
2. В папке проекта: `npm install`
3. Запуск: `npm start`  ·  Сборка приложения: `npm run dist` (zip с Veil.app появится в `dist/`)
4. Если macOS не открывает собранное приложение: `xattr -cr Veil.app`

В приложении: нажмите на «Amsterdam» → вставьте ссылку `vpn://…` (из `sudo vpnctl add mac` на сервере) → «Сохранить» → кнопка питания.
Подключение выполняет `wg-quick`, поэтому macOS спросит пароль администратора.
