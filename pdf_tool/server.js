const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'templates')));

// ユーザーごとのデータをメモリに保存
// 形式: { "IPアドレス": { count: 0, date: "2024/1/1", isVip: false } }
const userStore = {};

// IPアドレスを取得する関数 (Renderなどのプロキシ環境対応)
const getIp = (req) => {
    return (req.headers['x-forwarded-for'] || req.connection.remoteAddress).split(',')[0].trim();
};

// 今日の日付文字列を取得
const getToday = () => new Date().toLocaleDateString('ja-JP');

// データ初期化・リセットチェック
const initUser = (ip) => {
    const today = getToday();
    if (!userStore[ip]) {
        userStore[ip] = { count: 0, date: today, isVip: false };
    } else if (userStore[ip].date !== today) {
        // 日付が変わっていたらカウントだけリセット（VIP権限は維持する場合）
        userStore[ip].count = 0;
        userStore[ip].date = today;
    }
    return userStore[ip];
};

// ステータス確認API
app.get('/api/status', (req, res) => {
    const ip = getIp(req);
    const user = initUser(ip);
    res.json({ count: user.count, is_vip: user.isVip, limit: 3 });
});

// カウント加算API
app.post('/api/increment', (req, res) => {
    const ip = getIp(req);
    const user = initUser(ip);

    if (user.count >= 3 && !user.isVip) {
        return res.status(403).json({ status: 'limit_reached' });
    }

    user.count++;
    res.json({ status: 'success', current_count: user.count });
});

// VIP解除API
app.post('/api/unlock', (req, res) => {
    const ip = getIp(req);
    const user = initUser(ip);

    // パスワード設定 (ここは自由に変更してください)
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
