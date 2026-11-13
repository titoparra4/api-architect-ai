const express = require('express');
const cors = require('cors');
const { authenticate } = require('./auth');
const claims = require('./routes/claims');

const app = express();
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '50mb' }));

app.get('/health', (req, res) => res.json({ status: 'ok' }));
app.use('/claims', authenticate, claims);

app.use((err, req, res, next) => {
  res.status(500).json({ message: err.message, stack: err.stack });
});

app.listen(process.env.PORT || 3000);
