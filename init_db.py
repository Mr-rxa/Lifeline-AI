import csv
import random
from datetime import datetime, timedelta
from extensions import db, bcrypt
from models import Hospital, User, Ambulance, Incident

def init_hospitals():
    if Hospital.query.first():
        return # Already initialized

    try:
        with open('hospitals.csv', 'r') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                if count >= 10: break # Only seed 10 for demo
                total_beds = random.randint(50, 200)
                total_icu = random.randint(10, 50)
                
                hosp = Hospital(
                    name=row['name'],
                    lat=float(row['lat']),
                    lon=float(row['lon']),
                    address=row.get('address', 'Delhi, India'),
                    total_beds=total_beds,
                    available_beds=random.randint(10, total_beds),
                    total_icu_beds=total_icu,
                    available_icu_beds=random.randint(2, total_icu),
                    ventilators_available=random.randint(2, 20)
                )
                db.session.add(hosp)
                count += 1
            db.session.commit()
            print("Successfully initialized hospital data.")
    except Exception as e:
        print(f"Error initializing hospitals: {e}")

def init_fleet_and_demo_data():
    if User.query.filter_by(role='driver').first():
        return
        
    print("Generating Judge Demo Mode data...")
    # Seed 10 Drivers and 10 Ambulances
    hospitals = Hospital.query.all()
    if not hospitals:
        return
        
    for i in range(1, 11):
        driver = User(
            username=f'driver{i}',
            email=f'driver{i}@lifeline.ai',
            password_hash=bcrypt.generate_password_hash('driver123').decode('utf-8'),
            role='driver'
        )
        db.session.add(driver)
        db.session.flush() # get ID
        
        # Give ambulances a location near hospitals
        hosp = random.choice(hospitals)
        lat = hosp.lat + random.uniform(-0.02, 0.02)
        lon = hosp.lon + random.uniform(-0.02, 0.02)
        
        amb = Ambulance(
            vehicle_number=f'AMB-{100+i}',
            driver_id=driver.id,
            status='available',
            type=random.choice(['ALS', 'BLS']),
            last_lat=lat,
            last_lon=lon,
            last_update=datetime.utcnow()
        )
        db.session.add(amb)
        
    # Seed 20 Historical Incidents for Analytics
    for i in range(1, 21):
        hosp = random.choice(hospitals)
        created = datetime.utcnow() - timedelta(days=random.randint(0, 7), hours=random.randint(1, 23))
        inc = Incident(
            patient_name=f'Historical Patient {i}',
            patient_phone='555-0199',
            patient_condition_notes=random.choice(['Accident', 'Cardiac Emergency', 'Trauma']),
            pickup_lat=hosp.lat + random.uniform(-0.05, 0.05),
            pickup_lon=hosp.lon + random.uniform(-0.05, 0.05),
            severity=random.choice(['normal', 'urgent', 'critical']),
            status='completed',
            target_hospital_id=hosp.id,
            created_at=created,
            dispatched_at=created + timedelta(minutes=1),
            en_route_pickup_at=created + timedelta(minutes=2),
            arrived_pickup_at=created + timedelta(minutes=10),
            en_route_hospital_at=created + timedelta(minutes=15),
            arrived_hospital_at=created + timedelta(minutes=25),
            completed_at=created + timedelta(minutes=30)
        )
        db.session.add(inc)

    # Seed 2 Active pending incidents
    for i in range(1, 3):
        hosp = random.choice(hospitals)
        inc = Incident(
            patient_name=f'Active Patient {i}',
            patient_phone='555-0100',
            patient_condition_notes=random.choice(['Stroke', 'Fire Injury']),
            pickup_lat=hosp.lat + random.uniform(-0.03, 0.03),
            pickup_lon=hosp.lon + random.uniform(-0.03, 0.03),
            severity='critical',
            status='pending',
            created_at=datetime.utcnow()
        )
        db.session.add(inc)
        
    db.session.commit()
    print("Demo data initialized.")

def init_admin():
    if User.query.filter_by(role='admin').first():
        return

    admin = User(
        username='admin',
        email='admin@lifeline.ai',
        password_hash=bcrypt.generate_password_hash('admin123').decode('utf-8'),
        role='admin'
    )
    db.session.add(admin)
    
    dispatch = User(
        username='dispatcher',
        email='disp@lifeline.ai',
        password_hash=bcrypt.generate_password_hash('admin123').decode('utf-8'),
        role='dispatcher'
    )
    db.session.add(dispatch)
    db.session.commit()
    print("Successfully created default admin and dispatcher.")
