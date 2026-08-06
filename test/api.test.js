const test = require('node:test');
const assert = require('node:assert/strict');
const ambulance = require('../api/ambulance');

test('ambulance API returns nearest hospital metadata', async () => {
  const req = { method: 'GET', query: { lat: '28.6139', lon: '77.2090' }, body: {} };
  const res = {
    statusCode: 200,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(payload) {
      this.payload = payload;
    }
  };

  ambulance(req, res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.payload.ok, true);
  assert.equal(res.payload.nearestHospital.name, 'Max Super Specialty');
});
