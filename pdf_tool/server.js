const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.json());

// templatesフォルダ内のファイルを公開するように設定
app.use(express.static(path.join(__dirname, 'templates')));

let count = 0;
let isVip = false;

app.get('/api/status', (req, res) => {
    res.json({ count, is_vip: isVip });
});

app.post('/api/increment', (req, res) => {
    count++;
    res.json({ status: 'success' });
});

app.post('/api/unlock', (req, res) => {
    const { password } = req.body;
    if (password === 'vip2026') {
        isVip = true;
        res.json({ status: 'success' });
    } else {
        res.status(401).json({ status: 'error' });
    }
});

// 全てのリクエストに対して templates/index.html を返す
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'index.html'));
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
