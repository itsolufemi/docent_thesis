import { StyleSheet, Dimensions } from 'react-native';

const { width, height } = Dimensions.get('window'); // window dimensions

export const styles = StyleSheet.create({
  main: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    backgroundColor: 'rgba(255, 255, 255, 0.93)',
  },

  section: {
    flex: 1,
    marginTop: 20,
    marginBottom: 20,
    alignItems: 'center',
    width: '100%',
  },

  scrollView: {
    width: '100%',
    height: height * 0.7,
    maxHeight: 600,
  },

  scrollViewMain: {
    width: '100%',
    height: height * 0.7,
    maxHeight: 600,
    marginTop:10
  },

  scrollViewFoot: {
    width: '100%',
    height: height * 0.7,
    maxHeight: 600,
    margin:10
  },
  
  scrollViewFootText: {
    overflow: 'auto',
    textAlign:'center',
    paddingTop: 200,
    paddingBottom: 5,
    width: '100%',
  },

  player: {
    alignItems :'center',
    width:'100%',
    borderColor: 'rgba(255, 255, 255, 0.5)',
    borderWidth: 0.5,
    justifyContent:'center',
    flexDirection:'row',
    gap:10,
  },

  roundButton: {
    borderColor: 'rgba(255, 255, 255, 0.5)',
    borderWidth: 0.5,
    backgroundColor: 'transparent',
    borderRadius: 50,
    padding: 10,
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },

disabledButton: {
  backgroundColor: '#d3d3d3', // light grey
  color: '#808080', // darker grey for text
  borderColor: '#a9a9a9', // dark grey border
  opacity: 0.6,               // semi-transparent
},

  greenBtn: {
    backgroundColor: 'seagreen',
  },

  icon: {
    color: 'black',
    fontSize: 15,
    fontWeight: '600',
  },

  questionBox: {
    paddingHorizontal: 20,
    paddingTop: 20,
    width: '100%',
    color: 'green',

  },

  textPanel: {
    overflow: 'auto',
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 40,
    width: '100%',
    textAlign: 'justify',
  },

  navigation: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 30,
    alignItems: 'center',
    position: 'absolute',
    bottom: 0,
    width: '100%',
    backgroundColor: 'white',
  },

  navButton: {
    width: 50,
    height: 30,
    margin: 10,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f0f0f0',
    borderRadius: 5,
    borderWidth: 0.3,
    borderColor: 'green',
  },
  closeButton: {
    backgroundColor: 'rgb(94, 31, 31)',
    width: 50,
    height: 30,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 5,
  },

  button: {
    borderColor: 'rgba(255, 255, 255, 0.5)',
    borderWidth: 0.5,
    backgroundColor: 'transparent',
    borderRadius: 50,
    padding: 10,
    width: 30,
    height: 30,
    justifyContent: 'center',
    alignItems: 'center',
    boxShadow: '0px 0px 20px rgba(0, 0, 0, 0.5)',
    transition: 'all 0.3s ease-in-out',
  },

  
  micButton: {
    color:'black',
  },

  recordingButton: {
    backgroundColor: '#4D7860', // Red color when recording
    width: 70,
    height: 50,
  },

  icon: {
    fontSize: 18, // Adjust the icon size as per your design
    color: '#000',
  },

  overlay: {
    width:'100%',
    alignItems:'center',
    opacity: 0.5,
  }
});
