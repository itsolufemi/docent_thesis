import React from 'react';
import MainApplication from './components/MainApplication.jsx';
import TicketForm from './components/TicketForm.jsx';
import LoginForm from './components/LoginForm.jsx';
import './styles.css';

export default function App() {

    return (
        <main className="app-shell">
            <div className="app-main">
                <h1 className="app-title">docent.ai</h1>
                {<MainApplication />}
                {/*<TicketForm />*/}
                {/*<LoginForm />*/ }
            </div>
        </main>
    );
}
