const express = require('express');
const path = require('path');
const app = express();

/**
 * 1. 最速レスポンス設定 (生存確認用)
 */
app.get('/ping', (req, res) => res.status(200).send('pong'));

// ポート設定
const PORT = process.env.PORT || 10000;

/**
 * 2. VIPパスワード設定の読み込み
 */
const getValidPasswords = () => {
    const rawPasswords = process.env.VIP_PASSWORD || "";
    return rawPasswords.split(',').map(p => p.trim()).filter(p => p !== "");
};

// 起動時に設定確認
const validPasswords = getValidPasswords();
if (validPasswords.length === 0) {
    console.warn("⚠️ Warning: VIP_PASSWORD environment variable is missing.");
}

/**
 * 3. ミドルウェア & 静的ファイル設定
 * 【重要】ルーティングの順番が SEO や画像表示の成否を分けます
 */
app.use(express.json());

// A. staticフォルダを最優先で公開 (OGP画像など)
// これにより /static/ogp-image.png が正しく画像として返されます
app.use('/static', express.static(path.join(__dirname, 'static')));

// B. templatesフォルダ内の静的ファイルを公開 (CSS/JSなど)
app.use(express.static(path.join(__dirname, 'templates')));

/**
 * 4. ユーザーデータ管理 (メモリ保存)
 */
const userStore = {};
const getToday = () => new Date().toLocaleDateString('ja-JP');

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

/**
 * 5. API エンドポイント
 */

// ステータス確認
app.get('/api/status', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);
    res.json({ 
        count: user.count, 
        is_vip: user.isVip, 
        limit: 3 
    });
});

// 使用回数カウントアップ
app.post('/api/increment', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    if (!deviceId) return res.status(400).json({ status: 'error', message: 'No Device ID' });

    const user = initUser(deviceId);

    if (!user.isVip && user.count >= 3) {
        return res.status(403).json({ status: 'limit_reached' });
    }

    user.count++;
    res.json({ status: 'success', current_count: user.count });
});

// VIP解除
app.post('/api/unlock', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);
    const inputPassword = req.body.password;
    const currentPasswords = getValidPasswords();
    
    if (currentPasswords.length === 0) {
        return res.status(500).json({ status: 'error', message: 'Server configuration error' });
    }

    if (currentPasswords.includes(inputPassword)) {
        user.isVip = true;
        res.json({ status: 'success' });
    } else {
        res.status(401).json({ status: 'error', message: 'Invalid password' });
    }
});

/**
 * 6. フロントエンドへのルーティング (最後にする)
 * 全てのAPIや静的ファイルに該当しなかった場合、index.html を返す
 */
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'index.html'));
});

/**
 * 7. サーバー起動
 */
app.listen(PORT, () => {
    console.log(`-----------------------------------------`);
    console.log(`🚀 AlphaSnap Server Running on Port: ${PORT}`);
    console.log(`📂 Static folder linked: /static`);
    console.log(`🔑 Valid Passwords Loaded: ${getValidPasswords().length}`);
    console.log(`-----------------------------------------`);
});
