"""Seed LifeLine AI with realistic data: 50 real Delhi-NCR hospitals, staff,
ambulances, and 14 days of historical incidents so every dashboard and chart
renders from real database rows.

Run:  python -m app.seed
This resets the database to a clean, deterministic demo dataset.
"""

import random
from datetime import timedelta

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Ambulance,
    AuditLog,
    Hospital,
    Incident,
    Resource,
    User,
    utcnow,
)

random.seed(42)

HOSPITALS = [
    ("AIIMS Delhi", 28.5672, 77.2100), ("Fortis Noida", 28.5708, 77.3345),
    ("Medanta Gurgaon", 28.4294, 77.0405), ("Max Saket", 28.5286, 77.2195),
    ("BLK Hospital", 28.6517, 77.1891), ("Safdarjung Hospital", 28.5677, 77.2089),
    ("Ram Manohar Lohia Hospital", 28.6264, 77.2147), ("Apollo Hospital Delhi", 28.5425, 77.2710),
    ("Fortis Vasant Kunj", 28.5147, 77.1598), ("Indraprastha Apollo", 28.5425, 77.2710),
    ("Sir Ganga Ram Hospital", 28.6423, 77.1892), ("Lok Nayak Hospital", 28.6336, 77.2313),
    ("Batra Hospital", 28.5003, 77.2515), ("Holy Family Hospital", 28.6494, 77.2128),
    ("Moolchand Hospital", 28.5713, 77.2502), ("Primus Super Speciality Hospital", 28.5363, 77.2664),
    ("Max Patparganj", 28.6296, 77.3024), ("Fortis Shalimar Bagh", 28.7267, 77.1632),
    ("Artemis Hospital Gurgaon", 28.4425, 77.0633), ("Paras Hospital Gurgaon", 28.4679, 77.0374),
    ("Columbia Asia Hospital Gurgaon", 28.4561, 77.0727), ("Max Hospital Vaishali", 28.6509, 77.3358),
    ("Yashoda Hospital Ghaziabad", 28.6637, 77.4538), ("Kailash Hospital Noida", 28.5355, 77.3910),
    ("Jaypee Hospital Noida", 28.6087, 77.3714), ("Shanti Mukand Hospital", 28.6128, 77.2941),
    ("Pushpawati Singhania Hospital", 28.5449, 77.3182), ("Sant Parmanand Hospital", 28.7084, 77.1161),
    ("Dr. Hedgewar Hospital", 28.6698, 77.2321), ("Venkateshwar Hospital Dwarka", 28.5921, 77.0462),
    ("Akash Healthcare Delhi", 28.5936, 77.0461), ("Dharamshila Narayana Hospital", 28.6413, 77.2998),
    ("Manipal Hospital Dwarka", 28.5921, 77.0463), ("Aakash Hospital Dwarka", 28.5937, 77.0460),
    ("Sanjeevan Hospital Ghaziabad", 28.6692, 77.4383), ("ESI Hospital Rohini", 28.7395, 77.1215),
    ("Saroj Hospital Rohini", 28.7496, 77.1160), ("Jaipur Golden Hospital Rohini", 28.7334, 77.1073),
    ("Shree Narayan Hospital Rohini", 28.7210, 77.1183), ("Majeedia Hospital", 28.6264, 77.2810),
    ("GTB Hospital", 28.6767, 77.3099), ("Deen Dayal Upadhyay Hospital", 28.6166, 77.2873),
    ("Northern Railway Central Hospital", 28.6445, 77.2167), ("St. Stephens Hospital", 28.6405, 77.2191),
    ("Cancer Institute", 28.5674, 77.2117), ("Indian Spinal Injuries Centre", 28.5678, 77.1694),
    ("Kalra Hospital Kirti Nagar", 28.6542, 77.1417), ("Jessa Ram Hospital", 28.6314, 77.2185),
    ("Tirath Ram Shah Hospital", 28.6692, 77.2150), ("Kalawati Saran Hospital", 28.6293, 77.2229),
]

DELHI_CENTER = (28.6139, 77.2090)
EMERGENCY_TYPES = ["cardiac", "trauma", "accident", "respiratory", "stroke", "obstetric", "medical"]
DESCRIPTIONS = {
    "cardiac": "Patient with severe chest pain, suspected heart attack, sweating",
    "trauma": "Road accident victim with deep cut and bleeding from the leg",
    "accident": "Two-wheeler collision, possible fracture and head injury",
    "respiratory": "Difficulty breathing, asthma patient, low oxygen",
    "stroke": "Sudden facial droop and slurred speech, suspected stroke",
    "obstetric": "Pregnant woman in active labor, contractions 3 minutes apart",
    "medical": "High fever and dehydration, patient feeling faint",
}
ADDRESSES = [
    "Connaught Place", "Karol Bagh", "Lajpat Nagar", "Saket District Centre", "Dwarka Sector 12",
    "Rohini Sector 7", "Vasant Kunj", "Mayur Vihar Phase 1", "Janakpuri", "Pitampura",
    "Nehru Place", "Hauz Khas", "Rajouri Garden", "Preet Vihar", "Greater Kailash",
]


def rand_point(spread=0.06):
    return DELHI_CENTER[0] + random.uniform(-spread, spread), DELHI_CENTER[1] + random.uniform(-spread, spread)


def severity_for(emergency_type, description):
    from app.services.ai_engine import predict_severity

    return predict_severity(emergency_type, description)


def run():
    print("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ---- Hospitals + resources ----
        hospitals = []
        for name, lat, lon in HOSPITALS:
            total_beds = random.randint(80, 320)
            total_icu = random.randint(8, 45)
            h = Hospital(
                name=name,
                lat=lat,
                lon=lon,
                address=f"{name}, Delhi NCR",
                phone=f"+91-11-{random.randint(20000000, 49999999)}",
                total_beds=total_beds,
                available_beds=random.randint(int(total_beds * 0.1), int(total_beds * 0.5)),
                total_icu_beds=total_icu,
                available_icu_beds=random.randint(0, max(1, int(total_icu * 0.4))),
                accepting=True,
            )
            db.add(h)
            db.flush()
            for rname, lo, hi in [("Ventilators", 4, 25), ("Oxygen Cylinders", 20, 120), ("Blood Units", 10, 80)]:
                tot = random.randint(lo, hi)
                db.add(Resource(hospital_id=h.id, name=rname, total=tot, available=random.randint(0, tot)))
            hospitals.append(h)
        db.commit()

        # ---- Core staff ----
        admin = User(full_name="System Administrator", email=settings.SEED_ADMIN_EMAIL,
                     phone="+91-9000000000", password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                     role="admin")
        dispatcher = User(full_name="Control Room Dispatcher", email="dispatcher@lifeline.ai",
                          phone="+91-9000000001", password_hash=hash_password("dispatch123"),
                          role="dispatcher")
        citizen = User(full_name="Rahul Sharma", email="citizen@lifeline.ai", phone="+91-9810000000",
                       password_hash=hash_password("citizen123"), role="citizen")
        db.add_all([admin, dispatcher, citizen])
        db.flush()

        # Hospital operators for the first 5 hospitals.
        for i in range(5):
            db.add(User(full_name=f"{hospitals[i].name} Operator", email=f"hospital{i + 1}@lifeline.ai",
                        phone=f"+91-981100000{i}", password_hash=hash_password("hospital123"),
                        role="hospital", hospital_id=hospitals[i].id))

        # ---- Drivers + ambulances ----
        ambulances = []
        for i in range(12):
            driver = User(full_name=f"Driver {i + 1}", email=f"driver{i + 1}@lifeline.ai",
                          phone=f"+91-982200000{i}", password_hash=hash_password("driver123"), role="driver")
            db.add(driver)
            db.flush()
            lat, lon = rand_point()
            on_shift = i < 9
            amb = Ambulance(
                vehicle_number=f"DL-AMB-{1000 + i}",
                type=random.choice(["ALS", "BLS"]),
                driver_id=driver.id,
                on_shift=on_shift,
                status="available" if on_shift else "offline",
                last_lat=lat if on_shift else None,
                last_lon=lon if on_shift else None,
                last_update=utcnow() if on_shift else None,
            )
            db.add(amb)
            ambulances.append(amb)
        db.commit()

        # ---- Historical incidents (last 14 days, completed) for analytics ----
        now = utcnow()
        completed = 0
        for _ in range(60):
            etype = random.choice(EMERGENCY_TYPES)
            desc = DESCRIPTIONS[etype]
            band, score = severity_for(etype, desc)
            plat, plon = rand_point(0.08)
            created = now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23),
                                      minutes=random.randint(0, 59))
            dispatched = created + timedelta(minutes=random.randint(1, 4))
            accepted = dispatched + timedelta(seconds=random.randint(20, 90))
            arrived_pickup = dispatched + timedelta(minutes=random.randint(5, 16))
            en_route_hosp = arrived_pickup + timedelta(minutes=random.randint(3, 12))
            arrived_hosp = en_route_hosp + timedelta(minutes=random.randint(8, 26))
            done = arrived_hosp + timedelta(minutes=random.randint(5, 15))
            amb = random.choice(ambulances)
            hosp = random.choice(hospitals)
            db.add(Incident(
                citizen_id=citizen.id, patient_name="Emergency Patient",
                patient_phone="+91-9810000000", emergency_type=etype, description=desc,
                pickup_lat=plat, pickup_lon=plon, pickup_address=random.choice(ADDRESSES),
                severity=band, severity_score=score, status="completed",
                assigned_ambulance_id=amb.id, target_hospital_id=hosp.id,
                created_at=created, dispatched_at=dispatched, accepted_at=accepted,
                arrived_pickup_at=arrived_pickup, en_route_hospital_at=en_route_hosp,
                arrived_hospital_at=arrived_hosp, completed_at=done,
            ))
            completed += 1

        # ---- A few live pending incidents currently in the dispatch queue ----
        for _ in range(4):
            etype = random.choice(EMERGENCY_TYPES)
            desc = DESCRIPTIONS[etype]
            band, score = severity_for(etype, desc)
            plat, plon = rand_point(0.05)
            db.add(Incident(
                citizen_id=citizen.id, patient_name="Walk-in Patient",
                patient_phone="+91-9811112222", emergency_type=etype, description=desc,
                pickup_lat=plat, pickup_lon=plon, pickup_address=random.choice(ADDRESSES),
                severity=band, severity_score=score, status="pending",
                created_at=now - timedelta(minutes=random.randint(1, 12)),
            ))

        db.add(AuditLog(actor="system", action="seed", entity="system", detail="Initial dataset seeded"))
        db.commit()

        print(f"Seed complete: {len(hospitals)} hospitals, {len(ambulances)} ambulances, "
              f"{completed} historical + 4 pending incidents.")
        print("\nLogin credentials:")
        print(f"  Admin       {settings.SEED_ADMIN_EMAIL} / {settings.SEED_ADMIN_PASSWORD}")
        print("  Dispatcher  dispatcher@lifeline.ai / dispatch123")
        print("  Driver      driver1@lifeline.ai / driver123")
        print("  Hospital    hospital1@lifeline.ai / hospital123")
        print("  Citizen     citizen@lifeline.ai / citizen123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
