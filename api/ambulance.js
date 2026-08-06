const hospitals = [
  { name: 'AIIMS Delhi', lat: 28.5672, lon: 77.2100 },
  { name: 'Fortis Hospital', lat: 28.5355, lon: 77.2197 },
  { name: 'Apollo Hospital', lat: 28.5667, lon: 77.2684 },
  { name: 'Max Super Specialty', lat: 28.6139, lon: 77.2090 }
];

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = (deg) => deg * (Math.PI / 180);
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function nearestHospital(lat, lon) {
  let best = null;
  let minDist = Infinity;
  for (const hospital of hospitals) {
    const dist = haversine(lat, lon, hospital.lat, hospital.lon);
    if (dist < minDist) {
      minDist = dist;
      best = hospital;
    }
  }
  return { hospital: best, distanceKm: Math.round(minDist * 10) / 10 };
}

module.exports = (req, res) => {
  const orsKey = process.env.ORS_API_KEY || '';

  if (req.method === 'GET') {
    const lat = Number(req.query.lat || 28.6139);
    const lon = Number(req.query.lon || 77.2090);
    const { hospital, distanceKm } = nearestHospital(lat, lon);
    res.status(200).json({
      ok: true,
      ambulance: 'Lifeline-AI',
      location: { lat, lon },
      nearestHospital: hospital,
      distanceKm,
      etaMinutes: Math.max(1, Math.round(distanceKm / 40)),
      orsConfigured: Boolean(orsKey)
    });
    return;
  }

  if (req.method === 'POST') {
    const body = req.body || {};
    const lat = Number(body.lat || 28.6139);
    const lon = Number(body.lon || 77.2090);
    const { hospital, distanceKm } = nearestHospital(lat, lon);
    res.status(200).json({ ok: true, received: body, nearestHospital: hospital, distanceKm, etaMinutes: Math.max(1, Math.round(distanceKm / 40)), orsConfigured: Boolean(orsKey) });
    return;
  }

  res.status(405).json({ ok: false, error: 'Method not allowed' });
};
