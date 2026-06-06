import React from 'react';
import { SafeAreaView, View, Text, StyleSheet} from 'react-native';
import MainApplication from './components/MainApplication.js';
import TicketForm from './components/TicketForm.js';
import LoginForm from './components/LoginForm.js';

export default function App() {

    return (
        <SafeAreaView style={styles.main}>
            <View style={styles.main}>
                <Text style={styles.title}>docent.ai</Text>
                {<MainApplication />}
                {/*<TicketForm />*/}
                {/*<LoginForm />*/ }
            </View>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    main: {
        flex: 1,
        justifyContent: 'center',
        backgroundColor: 'rgba(255, 255, 255, 0.93)',
    },
    title: {
        textAlign: 'center',
        fontSize: 15,
        fontWeight: '300',
        padding: 20,
        color: '#5c5c5c',
    },
});
