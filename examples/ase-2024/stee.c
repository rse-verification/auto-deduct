/*
    This module controls the steering system of vehicles.

    The following is a list of requirements it should adhere to.

    Req. 1:
    If the primary circuit has no flow
    or a short circuit is detected
    then the primary circuit cannot provide power steering.

    Req. 2:
    The vehicle is considered to be moving
    if the wheel based speed signal is greater than 3 km/h.

    Req. 3:
    If the vehicle is moving
    and the primary circuit cannot provide power steering
    then the vehicle is moving without primary power steering.

    Req. 4:
    If the vehicle is moving without primary power steering
    then the secondary circuit should handle power steering.

    Req. 5:
    If the secondary circuit is providing power steering
    and the parking brake is not set
    then the electric motor must be activated.
 */

// #define _(...) /* nothing */
//
// #define VEH_MOVING_LIMIT 3
//
// #define TRUE 1
// #define FALSE 0

enum SENSOR_STATE
{
    WORKING,
    NO_FLOW,
    SHORT_CIRCUIT
};

struct VEHICLE_INFO
{
    int wheelSpeed;
    int parkingBrake;
    int primLowFlow;
    int primHighVoltage;
    int secondCircHandlesStee;
    int electricMotorAct;
};

enum SIGNAL
{
    PARKING_BRAKE_APPLIED,
    PRIMARY_CIRCUIT_LOW_FLOW,
    PRIMARY_CIRCUIT_HIGH_VOLTAGE,
    WHEEL_BASED_SPEED,
    SECONDARY_CIRCUIT_HANDLES_STEERING,
    ELECTRIC_MOTOR_ACTIVATED,
    NUM_SIGNALS
};

// ghost variables representing model_variables in requirements
// note: these should all be booleans
//@ ghost int model_vehicleIsMoving;
//@ ghost int model_vehicleMovingWithoutPrimaryPowerSteering;
//@ ghost int model_primaryCircuitProvidingPowerSteering;

int state_PARKING_BRAKE_APPLIED;
int state_PRIMARY_CIRCUIT_LOW_FLOW;
int state_PRIMARY_CIRCUIT_HIGH_VOLTAGE;
int state_WHEEL_BASED_SPEED;
int state_SECONDARY_CIRCUIT_HANDLES_STEERING;
int state_ELECTRIC_MOTOR_ACTIVATED;

//int state[NUM_SIGNALS]; // Global state

/*
    Reads the specified signal from the state.
 */
int read(enum SIGNAL idx)
{
    if(idx < NUM_SIGNALS)
    {
        if(idx == PARKING_BRAKE_APPLIED)
            return state_PARKING_BRAKE_APPLIED;
        if(idx == PRIMARY_CIRCUIT_LOW_FLOW)
            return state_PRIMARY_CIRCUIT_LOW_FLOW;
        if(idx == PRIMARY_CIRCUIT_HIGH_VOLTAGE)
            return state_PRIMARY_CIRCUIT_HIGH_VOLTAGE;
        if(idx == WHEEL_BASED_SPEED)
            return state_WHEEL_BASED_SPEED;
        if(idx == SECONDARY_CIRCUIT_HANDLES_STEERING)
            return state_SECONDARY_CIRCUIT_HANDLES_STEERING;
        if(idx == ELECTRIC_MOTOR_ACTIVATED)
            return state_ELECTRIC_MOTOR_ACTIVATED;
    }
    return -1;
}

/*
    Writes the specified signal to the state.
 */
void write(enum SIGNAL idx, int val)
{
    if(idx < NUM_SIGNALS)
    {
        if(idx == PARKING_BRAKE_APPLIED)
            state_PARKING_BRAKE_APPLIED = val;
        if(idx == PRIMARY_CIRCUIT_LOW_FLOW)
            state_PRIMARY_CIRCUIT_LOW_FLOW = val;
        if(idx == PRIMARY_CIRCUIT_HIGH_VOLTAGE)
            state_PRIMARY_CIRCUIT_HIGH_VOLTAGE = val;
        if(idx == WHEEL_BASED_SPEED)
            state_WHEEL_BASED_SPEED = val;
        if(idx == SECONDARY_CIRCUIT_HANDLES_STEERING)
            state_SECONDARY_CIRCUIT_HANDLES_STEERING = val;
        if(idx == ELECTRIC_MOTOR_ACTIVATED)
            state_ELECTRIC_MOTOR_ACTIVATED = val;
    }
}

/*
    Reads the current state of the system.
 */
struct VEHICLE_INFO get_system_state()
{
    struct VEHICLE_INFO veh_info;
    veh_info.wheelSpeed = read(WHEEL_BASED_SPEED);
    veh_info.parkingBrake = read(PARKING_BRAKE_APPLIED);
    veh_info.primLowFlow = read(PRIMARY_CIRCUIT_LOW_FLOW);
    veh_info.primHighVoltage = read(PRIMARY_CIRCUIT_HIGH_VOLTAGE);
    veh_info.secondCircHandlesStee = read(SECONDARY_CIRCUIT_HANDLES_STEERING);
    veh_info.electricMotorAct = read(ELECTRIC_MOTOR_ACTIVATED);
    return veh_info;
}

/*
    Evaluates the state of the primary steering circuit sensors.
 */
enum SENSOR_STATE eval_prim_sensor_state(struct VEHICLE_INFO veh_info)
{
    enum SENSOR_STATE sensor_state;
    if(veh_info.primHighVoltage == 1)
    {
        sensor_state = SHORT_CIRCUIT;
    }
    else if(veh_info.primLowFlow == 1)
    {
        sensor_state = NO_FLOW;
    }
    else
    {
        sensor_state = WORKING;
    }
    return sensor_state;
}

/*
    Evaluates whether steering should be
    handled by the secondary circuit.
 */
struct VEHICLE_INFO secondary_steering(struct VEHICLE_INFO veh_info, enum SENSOR_STATE sensor_state)
{
    char vehicleIsMoving;
    char vehicleIsMovingWithoutPrimaryPowerSteering;


    // Check whether the vehicle is moving.
    if(veh_info.wheelSpeed > 3)
    {
        vehicleIsMoving = 1;
    }
    else
    {
        vehicleIsMoving = 0;
    }

    // Check whether vehicle is moving without primary power steering.
    if(vehicleIsMoving == 1 &&
      (sensor_state == NO_FLOW || sensor_state == SHORT_CIRCUIT))
    {
        vehicleIsMovingWithoutPrimaryPowerSteering = 1;
    }
    else
    {
        vehicleIsMovingWithoutPrimaryPowerSteering = 0;
    }

    // Let secondary circuit handle steering if necessary.
    if(vehicleIsMovingWithoutPrimaryPowerSteering == 1)
    {
        veh_info.secondCircHandlesStee = 1;
    }

    // Activate the electric motor.
    if(veh_info.secondCircHandlesStee == 1
        && veh_info.parkingBrake == 0)
    {
       veh_info.electricMotorAct = 1;
    }

    //@ ghost model_vehicleMovingWithoutPrimaryPowerSteering = vehicleIsMovingWithoutPrimaryPowerSteering;
    //@ ghost model_vehicleIsMoving = vehicleIsMoving;
    return veh_info;
}

/*
    Module entry point function.
 */
/*@
    // requires \valid(state + (0..NUM_SIGNALS-1));
    decreases 0;
    assigns
            state_PARKING_BRAKE_APPLIED,
            state_PRIMARY_CIRCUIT_LOW_FLOW,
            state_PRIMARY_CIRCUIT_HIGH_VOLTAGE,
            state_WHEEL_BASED_SPEED,
            // the above should not really need to be here
            state_SECONDARY_CIRCUIT_HANDLES_STEERING, state_ELECTRIC_MOTOR_ACTIVATED,
            model_vehicleIsMoving, model_vehicleMovingWithoutPrimaryPowerSteering,
            model_primaryCircuitProvidingPowerSteering;

    // Req. 1-4 without intermediary variables *
    ensures (\old(state_PRIMARY_CIRCUIT_HIGH_VOLTAGE) == 1
          || \old(state_PRIMARY_CIRCUIT_LOW_FLOW) == 1)
            && \old(state_WHEEL_BASED_SPEED) > 3
            ==> state_SECONDARY_CIRCUIT_HANDLES_STEERING == 1;

    // Req. 1 *
    ensures (\old(state_PRIMARY_CIRCUIT_HIGH_VOLTAGE) == 1
          || \old(state_PRIMARY_CIRCUIT_LOW_FLOW) == 1)
               ==> model_primaryCircuitProvidingPowerSteering == 0;

    // Req. 2
    ensures \old(state_WHEEL_BASED_SPEED) > 3
            ==> model_vehicleIsMoving == 1;

    // Req. 3
    ensures model_vehicleIsMoving == 1
            && model_primaryCircuitProvidingPowerSteering == 0
            ==> model_vehicleMovingWithoutPrimaryPowerSteering == 1;

    // Req. 4
    ensures model_vehicleMovingWithoutPrimaryPowerSteering == 1
            ==> state_SECONDARY_CIRCUIT_HANDLES_STEERING == 1;

    // Req. 5
    ensures state_SECONDARY_CIRCUIT_HANDLES_STEERING == 1
            && \old(state_PARKING_BRAKE_APPLIED) == 0
            ==> state_ELECTRIC_MOTOR_ACTIVATED == 1;
  */
void main()
{
    struct VEHICLE_INFO veh_info;
    enum SENSOR_STATE prim_sensor;

    veh_info = get_system_state();


    prim_sensor = eval_prim_sensor_state(veh_info);
    //@ ghost model_primaryCircuitProvidingPowerSteering = (prim_sensor == WORKING);

    veh_info = secondary_steering(veh_info, prim_sensor);

    write(SECONDARY_CIRCUIT_HANDLES_STEERING, veh_info.secondCircHandlesStee);
    write(ELECTRIC_MOTOR_ACTIVATED, veh_info.electricMotorAct);
}
