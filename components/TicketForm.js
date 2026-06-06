import React, { useState } from "react";
import { View, Text, TouchableOpacity, TextInput, StyleSheet } from "react-native";
import { ipv4 } from "./utils/ipv4_module.js";

export default function TicketForm() {
  const [tickets, setTickets] = useState(1);
  const [email, setEmail] = useState("");

  const increment = () => setTickets((t) => t + 1);
  const decrement = () => setTickets((t) => Math.max(1, t - 1));

  const onSubmit = async () => {
    try {
        const res = await fetch(`http://${ipv4}:4000/new_user`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, tickets }),
        });
        const response = await res.json();
        if (response.success) {
            console.log(`${tickets} ticket(s) purchased for ${email}`);
            console.log(`codes: ${response.codes}`);
        } else {
            console.log('failed to add user');
        }
    } catch (error) {
        console.error('error :', error);
        return;
    }
  };

  return (
    <View style={styles.container}>
      {/* Ticket Selector */}
      <View style={styles.ticketRow}>
        <Text style={{ fontSize: 15, borderWidth: 1, borderColor: "#ccc", borderRadius: 5, padding: 10}}>Tickets </Text>
        <TouchableOpacity onPress={decrement} style={styles.button}>
          <Text style={styles.buttonText}>−</Text>
        </TouchableOpacity>
        <Text style={styles.tickets}>{tickets}</Text>
        <TouchableOpacity onPress={increment} style={styles.button}>
          <Text style={styles.buttonText}>＋</Text>
        </TouchableOpacity>
      </View>

      {/* Email Input */}
      <View style= {styles.ticketRow}>
        <TextInput
            style={styles.input}
            placeholder="Enter your email"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
        />

        {/* Checkout Button */}
        <TouchableOpacity onPress={onSubmit} style={styles.checkoutButton}>
            <Text style={styles.checkoutText}>✔</Text>
        </TouchableOpacity>
        </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    padding: 20,
  },
  ticketRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 70,
    width: "80%",
    justifyContent: "space-between",
  },
  tickets: {
    fontSize: 15,
    marginHorizontal: 15,
  },
  button: {
    backgroundColor: "#ddd",
    padding: 10,
    borderRadius: 5,
  },
  buttonText: {
    fontSize: 10,
  },
  input: {
    width: "85%",
    borderWidth: 1,
    borderColor: "#ccc",
    padding: 10,
    borderRadius: 5,
   // marginBottom: 50,
  },
  checkoutButton: {
    width: "13%",
    backgroundColor: "seagreen",
    padding: 10,
    borderRadius: 5,
  },
  checkoutText: {
    color: "white",
    fontSize: 15,
  },
});
