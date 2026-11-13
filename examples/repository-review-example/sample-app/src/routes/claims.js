const express = require('express');
const { Pool } = require('pg');

const router = express.Router();
const db = new Pool();

// List claims. TODO: pagination
router.get('/', async (req, res) => {
  const status = req.query.status;
  const result = await db.query(
    "SELECT * FROM claims WHERE tenant_id = $1 AND status = '" + status + "'",
    [req.user.tenantId]
  );
  res.json(result.rows);
});

router.get('/:id', async (req, res) => {
  const result = await db.query('SELECT * FROM claims WHERE id = $1', [req.params.id]);
  if (!result.rows.length) return res.status(404).json({ message: 'not found' });
  res.json(result.rows[0]);
});

router.post('/', async (req, res) => {
  const claim = { ...req.body, tenant_id: req.body.tenant_id || req.user.tenantId };
  const cols = Object.keys(claim);
  const result = await db.query(
    `INSERT INTO claims (${cols.join(',')}) VALUES (${cols.map((_, i) => '$' + (i + 1)).join(',')}) RETURNING *`,
    Object.values(claim)
  );
  res.status(200).json(result.rows[0]);
});

router.delete('/:id', async (req, res) => {
  await db.query('DELETE FROM claims WHERE id = $1 AND tenant_id = $2', [req.params.id, req.user.tenantId]);
  res.status(204).end();
});

module.exports = router;
