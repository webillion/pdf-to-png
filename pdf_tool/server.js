const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3000;

// 静的ファイルの提供（index.htmlを表示）
app.use(express.static(path.join(__dirname, 'public')));

// cron-job.org 用の生存確認（これだけでOK）
app.get('/ping', (req, res) => {
    res.status(200).send('pong');
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
