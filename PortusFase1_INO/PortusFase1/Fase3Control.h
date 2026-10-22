#ifndef FASE3_CONTROL_H
#define FASE3_CONTROL_H
#include <Arduino.h>
void fase3_init();
void fase3_update();
bool fase3_command(const String &command);
bool fase3_gate_enabled();
void fase3_gate_begin();
int fase3_gate_decision(); // 0 pendiente, 1 autorizar, -1 rechazar
unsigned long fase3_gate_wait_ms();
uint8_t fase3_gate_retention();
String fase3_gate_plate();
String fase3_gate_label();
#endif
