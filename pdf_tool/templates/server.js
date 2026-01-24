const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 10000; // Renderは10000番ポートを期待します

app.use(express.json());
app.use(express.static(__dirname)); // index.htmlがある場所

// ダミーのAPIデータ（保存機能が必要な場合はデータベースが必要ですが、まずはこれで動きます）
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
    if (password === 'vip2026') { // パスコードをここで設定
        isVip = true;
        res.json({ status: 'success' });
    } else {
        res.status(401).json({ status: 'error' });
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
