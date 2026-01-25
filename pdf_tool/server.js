const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'templates')));

// ユーザーデータ (メモリ管理)
// キーをIPではなく「デバイスID」にします
const userStore = {};

const getToday = () => new Date().toLocaleDateString('ja-JP');

// ユーザー初期化 (IDベース)
const initUser = (deviceId) => {
    const today = getToday();
    // IDがない場合は空のオブジェクトを返す（カウント不可）
    if (!deviceId) return { count: 3, date: today, isVip: false }; 

    if (!userStore[deviceId]) {
        userStore[deviceId] = { count: 0, date: today, isVip: false };
    } else if (userStore[deviceId].date !== today) {
        // 日付が変わったらリセット
        userStore[deviceId].count = 0;
        userStore[deviceId].date = today;
        userStore[deviceId].isVip = false; // VIPもリセットする場合
    }
    return userStore[deviceId];
};

app.get('/api/status', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);
    res.json({ count: user.count, is_vip: user.isVip, limit: 3 });
});

app.post('/api/increment', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    if (!deviceId) return res.status(400).json({ status: 'error', message: 'No ID' });

    const user = initUser(deviceId);

    if (user.count >= 3 && !user.isVip) {
        return res.status(403).json({ status: 'limit_reached' });
    }

    user.count++;
    res.json({ status: 'success', current_count: user.count });
});

app.post('/api/unlock', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);

    // パスワード判定 (環境変数などに入れるとなお良いですが、簡易版として直書き)
    if (req.body.password === 'vip2026') {
        user.isVip = true;
        res.json({ status: 'success' });
    } else {
        res.status(401).json({ status: 'error' });
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'index.html'));
});

app.listen(PORT, () => console.log(`Server running on ${PORT}`));
