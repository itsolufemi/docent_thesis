import React, { useState } from "react";
import { View, Text, TouchableOpacity, TextInput, StyleSheet } from "react-native";
import { ipv4 } from "./utils/ipv4_module.js";

export default function LoginForm() {
  const [code, setCode] = useState("");

  const onSubmit = async () => {
    try {
        const res = await fetch(`http://${ipv4}:4000/login_user`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
        });
        const response = await res.json();
        if (response.success) {
        console.log(`login successful for code ${code}`);
        } else {
            console.log(`login failed, check code ${code}`);
        }
    } catch (error) {
        console.error('error :', error);
        return;
    }
  };

  return (
    <View style={styles.container}>
      <View style= {styles.ticketRow}>
            <TextInput
                style={styles.input}
                placeholder="Enter your code"
                value={code}
                onChangeText={setCode}
                keyboardType="numeric"
            />

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