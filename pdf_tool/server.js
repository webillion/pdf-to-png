const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'templates')));

let count = 0;
let isVip = false;

app.get('/api/status', (req, res) => {
    res.json({ count, is_vip: isVip });
});

app.post('/api/increment', (req, res) => {
    if (count >= 3 && !isVip) return res.status(403).json({ status: 'limit_reached' });
    count++;
    res.json({ status: 'success', current_count: count });
});

app.post('/api/unlock', (req, res) => {
    if (req.body.password === 'vip2026') { isVip = true; res.json({ status: 'success' }); }
    else res.status(401).json({ status: 'error' });
});

app.get('*', (req, res) => { res.sendFile(path.join(__dirname, 'templates', 'index.html')); });

app.listen(PORT, () => console.log(`Server running on ${PORT}`));
