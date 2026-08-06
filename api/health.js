module.exports = (req, res) => {
  res.status(200).json({ ok: true, service: 'lifeline-ai', mode: 'vercel' });
};
