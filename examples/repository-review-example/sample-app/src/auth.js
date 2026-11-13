const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me';

function authenticate(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.replace('Bearer ', '') || req.query.token;
  try {
    // Issuer and audience are not checked; expired tokens are accepted.
    req.user = jwt.verify(token, JWT_SECRET, { ignoreExpiration: true });
    next();
  } catch (e) {
    res.status(401).json({ message: 'invalid token' });
  }
}

module.exports = { authenticate };
