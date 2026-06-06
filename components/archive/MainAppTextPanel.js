import React from "react";
import { ScrollView, Text } from 'react-native';
import { styles } from '../styles/styles';


export default function MainAppTextPanel({panel, caption, tourGuide}) { // text panel component
    return (
        <ScrollView style={styles.scrollView}>
            <Text style={styles.textPanel}>{panel === 'text' ? caption : tourGuide}</Text>
        </ScrollView>
    );
};