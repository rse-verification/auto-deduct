#include <stdio.h>

// CC parameters
#define MIN_SPEED 20
#define MAX_SPEED 120
#define SPEED_INCREMENT 5
#define MAX_THROTTLE_SATURATION 100
#define MIN_PEDAL_PRESS_DETECTION 10

// CC states
enum CCState { OFF, ON, STDBY };

// CC variables
int cruiseSpeed = 0;
int carSpeed = 0;
int throttleCommand = 0;
enum CCState ccState = OFF;
int acceleratorPedal = 0;
int brakePedal = 0;

// Function to update CC state
void updateCCState() {
    if (ccState == OFF) {
        if (carSpeed >= MIN_SPEED && carSpeed <= MAX_SPEED && acceleratorPedal < MIN_PEDAL_PRESS_DETECTION) {
            ccState = ON;
            cruiseSpeed = carSpeed;
        }
    } else if (ccState == ON) {
        if (acceleratorPedal >= MIN_PEDAL_PRESS_DETECTION || carSpeed < MIN_SPEED || carSpeed > MAX_SPEED) {
            ccState = STDBY;
        } else if (brakePedal >= MIN_PEDAL_PRESS_DETECTION) {
            ccState = OFF;
        }
    } else if (ccState == STDBY) {
        if (acceleratorPedal < MIN_PEDAL_PRESS_DETECTION && carSpeed >= MIN_SPEED && carSpeed <= MAX_SPEED) {
            ccState = ON;
        }
    }
}

// Function to update throttle command
void updateThrottleCommand() {
    if (ccState == ON) {
        throttleCommand = (cruiseSpeed - carSpeed) * MAX_THROTTLE_SATURATION / (MAX_SPEED - MIN_SPEED);
        if (throttleCommand > MAX_THROTTLE_SATURATION) {
            throttleCommand = MAX_THROTTLE_SATURATION;
        }
    } else {
        throttleCommand = 0;
    }
}

// Main function
int main() {
    // Simulate car and driver actions
    carSpeed = 50;
    acceleratorPedal = 0;
    brakePedal = 0;
    updateCCState();
    updateThrottleCommand();
    printf("CC State: %d, Cruise Speed: %d, Throttle Command: %d\n", ccState, cruiseSpeed, throttleCommand);
    return 0;
}
