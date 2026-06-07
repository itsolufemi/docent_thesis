import React, { useState } from 'react';
import { ipv4 } from './utils/ipv4_module.js';

export default function TicketForm() {
  const [tickets, setTickets] = useState(1);
  const [email, setEmail] = useState('');

  const increment = () => setTickets((current) => current + 1);
  const decrement = () => setTickets((current) => Math.max(1, current - 1));

  const onSubmit = async () => {
    try {
      const res = await fetch(`http://${ipv4}:4000/new_user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      console.error('error:', error);
    }
  };

  return (
    <form className="ticket-form" onSubmit={(event) => event.preventDefault()}>
      <div className="form-row">
        <span className="ticket-label">Tickets</span>
        <button type="button" className="form-button" onClick={decrement}>
          -
        </button>
        <span className="ticket-count">{tickets}</span>
        <button type="button" className="form-button" onClick={increment}>
          +
        </button>
      </div>

      <div className="form-row">
        <input
          className="text-input"
          placeholder="Enter your email"
          value={email}
          type="email"
          onChange={(event) => setEmail(event.target.value)}
        />
        <button type="button" className="checkout-button" onClick={onSubmit}>
          Check
        </button>
      </div>
    </form>
  );
}
