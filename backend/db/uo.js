const fs = require('fs'); //import the file system module to read and write to the users database file
const users_db = require('./users.json'); //import the users database
const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

//#region server
const PORT = 4000;  
app.listen(PORT, () => {
    console.log(`user db server running on port ${PORT}`);
});

app.post("/new_user", (req, res) => { // add new user endpoint
    const { email, tickets } = req.body; //get email and number of codes tickets to generate codes for
    if (!email || !tickets) {
        return res.status(400).json({ error: "Email and number of tickets are required" });
    }
    try {
        const codes = new_user(email, tickets); //create a new user and get the generated codes
        res.json({ success: true, codes }); //return the generated codes
    } catch (error) {
        console.error("Error creating new user:", error);  
        return res.status(500).json({ error: "Internal server error" });
    }
});

app.post("/login_user", (req, res) => { // login user endpoint
    const { code } = req.body; //get the code to validate
    if (!code) {
        return res.status(400).json({ error: "code is required" });
    }
    try {
        res.json({ success: login_user(code) }); //return true if code is valid, otherwise return false
    } catch (error) {
        console.error("Error logging in user:", error);
        return res.status(500).json({ error: "Internal server error" });
    }
});
//#endregion

//#region user handling operation functions
const find_user = (email) => { //function to find a user in the users database
    const found_user = users_db.find(user => user.email === email); //return the user if found, otherwise return undefined
    if (found_user) return found_user;
    else console.log(`user not found, check email ${email}`);
    return null;
};

const new_user = (email, x) => { //function to add a new user to the users database
    const codes = generate_code(x); //generate x unique 6-digit codes
    users_db.push({ email, codes }); //add the new user to the users database
    console.log(`New user added: ${email}`);
    update_db(); //update the users database file
    return codes; //return the generated codes
};

const generate_code = (x) => { //function to generate x unique 6-digit codes
  const codes = [];
  // Generate a random number between 100000 and 999999x x number of times
    while (codes.length < x) {
        const code  = Math.floor(100000 + Math.random() * 900000).toString();
        if (!codes.includes(code)) {
            codes.push(code);
        }
    }
    return codes;
}

const login_user = (code) => { //function to login user by checking code against an existing user
    const found_user = users_db.find(user => user.codes.includes(code)); //return the user if code includes the argument
    if (found_user) return true;
    else console.log(`invalid ${code}`);
    return null;
}

const delete_user = (code) => { //function to delete a user from the users database
    const user_index = users_db.findIndex(user => user.codes === code); //find the index of the user to be deleted
    if (user_index !== -1) {
        const deleted_user = users_db.splice(user_index, 1); //remove the user from the users database
        fs.writeFileSync('./backend/db/users.json', JSON.stringify(users_db, null, 2)); //write the updated users database to the file
        console.log(`User deleted: ${deleted_user[0].email}`);
    } else {
        console.log(`user not found, check code ${code}`);
    }

    return;
}

const update_db = () => {
    fs.writeFileSync('./users.json', JSON.stringify(users_db, null, 1)); //write the updated users database to the file
}

module.exports = { new_user, login_user};
//#endregion

/* //testing th new user function.
new_user('odd@gmail.com', generate_code(2))
console.log(users_db)
*/

//console.log(login_user('222222')) //test the code retrieval function

//console.log(generate_code(3)) //test the code generation function

//console.log(login_user('4225552')) //test the login function
