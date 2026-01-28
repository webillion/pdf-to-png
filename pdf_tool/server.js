const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3000;

// index.html がある場所（このファイルと同じ階層）を公開する設定に変更
app.use(express.static(__dirname));

// 「/」にアクセスが来た時に index.html を確実に返す設定
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// cron-job.org 用の生存確認
app.get('/ping', (req, res) => {
    res.status(200).send('pong');
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
