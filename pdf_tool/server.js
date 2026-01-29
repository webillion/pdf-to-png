const express = require('express');
const path = require('path');
const app = express();

// ↓ ここ！一番最初に書くことで、最速で返事をします
app.get('/ping', (req, res) => res.status(200).send('pong'));

const PORT = process.env.PORT || 10000;

// 環境変数からパスワードを取得
const VIP_PASSWORD = process.env.VIP_PASSWORD;

if (!VIP_PASSWORD) {
    console.warn("⚠️ 警告: 環境変数 'VIP_PASSWORD' が設定されていません。VIP認証機能は動作しません。");
}

app.use(express.json());

app.use(express.static(path.join(__dirname, 'templates')));

// ユーザーデータ (メモリ管理: デバイスIDベース)
const userStore = {};

const getToday = () => new Date().toLocaleDateString('ja-JP');

// ユーザー初期化
const initUser = (deviceId) => {
    const today = getToday();
    if (!deviceId) return { count: 3, date: today, isVip: false }; 

    if (!userStore[deviceId]) {
        userStore[deviceId] = { count: 0, date: today, isVip: false };
    } else if (userStore[deviceId].date !== today) {
        userStore[deviceId].count = 0;
        userStore[deviceId].date = today;
        userStore[deviceId].isVip = false; 
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

// VIP解除API (環境変数を使用)
app.post('/api/unlock', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);

    // サーバー側の設定ミス防止チェック
    if (!VIP_PASSWORD) {
        return res.status(500).json({ status: 'error', message: 'Server configuration error' });
    }

    // 環境変数と比較
    if (req.body.password === VIP_PASSWORD) {
        user.isVip = true;
        res.json({ status: 'success' });
    } else {
        res.status(401).json({ status: 'error' }); // パスワード不一致
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'index.html'));
});

// --- ここを追加 ---
// 生存確認（Health Check）用の軽量API
// cron-job.org には このURL (https://あなたのURL/health) を登録する
app.get('/health', (req, res) => {
    res.status(200).send('OK');
});
// ----------------

app.listen(PORT, () => console.log(`Server running on ${PORT}`));
