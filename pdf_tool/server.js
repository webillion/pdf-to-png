const express = require('express');
const path = require('path');
const app = express();

/**
 * 1. 最速レスポンス設定 (cron-job.org / 生存確認用)
 * 他の処理よりも前に書くことで、サーバーが起きていることを即座に証明します。
 */
app.get('/ping', (req, res) => res.status(200).send('pong'));

// Renderのデフォルトポート、または10000番を使用
const PORT = process.env.PORT || 10000;

/**
 * 2. 複数パスワードの読み込み
 * 環境変数 VIP_PASSWORD をカンマ区切りでリスト化します。
 * 例: "pass1,pass2,pass3" -> ["pass1", "pass2", "pass3"]
 */
const getValidPasswords = () => {
    const rawPasswords = process.env.VIP_PASSWORD || "";
    return rawPasswords.split(',').map(p => p.trim()).filter(p => p !== "");
};

// 起動時に設定を確認
const validPasswords = getValidPasswords();
if (validPasswords.length === 0) {
    console.warn("⚠️ 警告: VIP_PASSWORD が設定されていません。VIP機能は利用できません。<br>Warning: VIP_PASSWORD environment variable is missing. Authentication functionality is unavailable.");
}

/**
 * 3. ミドルウェア設定
 */
app.use(express.json());
// index.htmlがtemplatesフォルダにある場合の静的ファイル設定
app.use(express.static(path.join(__dirname, 'templates')));

/**
 * 4. ユーザーデータ管理 (メモリ上の簡易保存)
 * ※サーバー再起動でリセットされますが、軽量化を優先しています。
 */
const userStore = {};
const getToday = () => new Date().toLocaleDateString('ja-JP');

const initUser = (deviceId) => {
    const today = getToday();
    // IDがない場合は制限モードで返す
    if (!deviceId) return { count: 3, date: today, isVip: false }; 

    if (!userStore[deviceId]) {
        userStore[deviceId] = { count: 0, date: today, isVip: false };
    } else if (userStore[deviceId].date !== today) {
        // 日付が変わっていたらカウントをリセット
        userStore[deviceId].count = 0;
        userStore[deviceId].date = today;
        // VIP状態は再起動や日付変更でリセットされる仕様（運用でカバー）
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

    // 非VIPかつ制限超えの場合
    if (!user.isVip && user.count >= 3) {
        return res.status(403).json({ status: 'limit_reached' });
    }

    user.count++;
    res.json({ status: 'success', current_count: user.count });
});

// VIP解除 (複数パスワード対応)
app.post('/api/unlock', (req, res) => {
    const deviceId = req.headers['x-device-id'];
    const user = initUser(deviceId);
    const inputPassword = req.body.password;

    // リストの最新版を取得して照合
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
 * 6. フロントエンドへのルーティング
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
    console.log(`🔑 Valid Passwords Loaded: ${getValidPasswords().length}`);
    console.log(`-----------------------------------------`);
});
