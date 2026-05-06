#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <ESP32Servo.h>

// ---------------- WIFI ----------------
#define WIFI_SSID "enter ssid"
#define WIFI_PASSWORD "password"

// ---------------- FIREBASE DETAILS ----------------
#define API_KEY "Your_API_Key"
#define DATABASE_URL "https://trash-iq-default-rtdb.firebaseio.com/"
#define USER_EMAIL "MAIL_ID"
#define USER_PASSWORD "Pass"

// Firebase objects
FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

// -------- SENSOR 1 (HUMAN DETECTION) --------
const int trigPin1 = 5;
const int echoPin1 = 18;

// -------- SENSOR 2 (BIO BIN LEVEL) --------
const int trigPin2 = 23;
const int echoPin2 = 22;

// -------- SENSOR 3 (NONBIO BIN LEVEL) --------
const int trigPin3 = 32;
const int echoPin3 = 33;

long duration1, duration2, duration3;
float distance1, distance2, distance3;

// -------- THRESHOLDS --------
#define HUMAN_THRESHOLD 20   // cm
#define BIN_FULL_LEVEL 10    // cm

// -------- SERVOS --------
Servo bioServo;
Servo nonBioServo;

int bioServoPin = 19;
int nonBioServoPin = 21;

String wasteType = "none";
bool humanDetected = false;

void setup() {

  Serial.begin(115200);

  // Sensor pins
  pinMode(trigPin1, OUTPUT);
  pinMode(echoPin1, INPUT);

  pinMode(trigPin2, OUTPUT);
  pinMode(echoPin2, INPUT);

  pinMode(trigPin3, OUTPUT);
  pinMode(echoPin3, INPUT);

  // Servo setup
  bioServo.attach(bioServoPin);
  nonBioServo.attach(nonBioServoPin);

  bioServo.write(0);
  nonBioServo.write(0);

  // -------- WIFI --------
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting WiFi");

  while (WiFi.status() != WL_CONNECTED){
    Serial.print(".");
    delay(300);
  }

  Serial.println("\nWiFi Connected");

  // -------- FIREBASE --------
  config.api_key = API_KEY;
  config.database_url = DATABASE_URL;

  auth.user.email = USER_EMAIL;
  auth.user.password = USER_PASSWORD;

  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
}

void loop(){

  if(!Firebase.ready()){
    delay(1000);
    return;
  }

  // -------- HUMAN DETECTION --------
  digitalWrite(trigPin1, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin1, LOW);

  duration1 = pulseIn(echoPin1, HIGH);
  distance1 = duration1 * 0.034 / 2;

  Serial.print("Human Distance: ");
  Serial.println(distance1);

  if(distance1 < HUMAN_THRESHOLD && distance1 > 0){
    humanDetected = true;
    Serial.println("Human Detected");
  } else {
    humanDetected = false;
  }

  // -------- BIO BIN LEVEL --------
  digitalWrite(trigPin2, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin2, LOW);

  duration2 = pulseIn(echoPin2, HIGH);
  distance2 = duration2 * 0.034 / 2;

  Serial.print("Bio Level: ");
  Serial.println(distance2);

  Firebase.RTDB.setFloat(&fbdo,"/trash_iq/bins/bio_level",distance2);

  // -------- NONBIO BIN LEVEL --------
  digitalWrite(trigPin3, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin3, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin3, LOW);

  duration3 = pulseIn(echoPin3, HIGH);
  distance3 = duration3 * 0.034 / 2;

  Serial.print("NonBio Level: ");
  Serial.println(distance3);

  Firebase.RTDB.setFloat(&fbdo,"/trash_iq/bins/nonbio_level",distance3);

  // -------- BIN FULL CHECK --------
  if(distance2 < BIN_FULL_LEVEL){
    Firebase.RTDB.setString(&fbdo,"/trash_iq/bins/bio_status","FULL");
  } else {
    Firebase.RTDB.setString(&fbdo,"/trash_iq/bins/bio_status","AVAILABLE");
  }

  if(distance3 < BIN_FULL_LEVEL){
    Firebase.RTDB.setString(&fbdo,"/trash_iq/bins/nonbio_status","FULL");
  } else {
    Firebase.RTDB.setString(&fbdo,"/trash_iq/bins/nonbio_status","AVAILABLE");
  }

  // -------- AI RESULT --------
  if(Firebase.RTDB.getString(&fbdo,"/trash_iq/ai_result/waste_type")){

    wasteType = fbdo.stringData();

    Serial.print("Waste Type: ");
    Serial.println(wasteType);

    if(humanDetected){

      // BIO BIN
      if(
        wasteType == "BIODEGRADABLE" ||
        wasteType == "PAPER" ||
        wasteType == "CARDBOARD"
      ){

        Serial.println("Opening Bio Bin");

        bioServo.write(90);
        delay(3000);
        bioServo.write(0);

        Firebase.RTDB.setString(&fbdo,"/trash_iq/ai_result/waste_type","none");
      }

      // NONBIO BIN
      else if(
        wasteType == "GLASS" ||
        wasteType == "METAL" ||
        wasteType == "PLASTIC" ||
        wasteType == "E-WASTE" ||
        wasteType == "OTHERS"
      ){

        Serial.println("Opening NonBio Bin");

        nonBioServo.write(90);
        delay(3000);
        nonBioServo.write(0);

        Firebase.RTDB.setString(&fbdo,"/trash_iq/ai_result/waste_type","none");
      }

    } else {
      Serial.println("Waiting for human...");
    }
  }

  delay(1500);
}
