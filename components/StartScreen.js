import React from "react";
import { View, Text, TouchableOpacity} from 'react-native';
import { styles } from './styles/styles';

export default function StartScreen({ loading, handleStartClick }) { // start screen
    return (
        <View style={styles.section}>
        <TouchableOpacity
            style={[styles.roundButton, loading && styles.greenBtn]}
            disabled={loading}
            onPress={handleStartClick}
        >
            <Text style={styles.icon}>{loading ? '...' : '▶'}</Text>
        </TouchableOpacity>
        </View>
    );
};  