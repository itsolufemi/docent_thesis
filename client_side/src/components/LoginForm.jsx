import React, { useState } from 'react';
import { ipv4 } from './utils/ipv4_module.js';

export default function LoginForm() {
  const [code, setCode] = useState('');

  const onSubmit = async () => {
    try {
      const res = await fetch(`http://${ipv4}:4000/login_user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const response = await res.json();

      if (response.success) {
        console.log(`login successful for code ${code}`);
      } else {
        console.log(`login failed, check code ${code}`);
      }
    } catch (error) {
      console.error('error:', error);
    }
  };

  return (
    <form className="login-form" onSubmit={(event) => event.preventDefault()}>
      <div className="form-row">
        <input
          className="text-input"
          placeholder="Enter your code"
          value={code}
          inputMode="numeric"
          onChange={(event) => setCode(event.target.value)}
        />
        <button type="button" className="checkout-button" onClick={onSubmit}>
          Check
        </button>
      </div>
    </form>
  );
}
