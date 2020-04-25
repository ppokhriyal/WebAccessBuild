from flask import render_template, url_for, flash, redirect, request, abort, session
from webaccessbuild import app, db, bcrypt
from webaccessbuild.forms import LoginForm,RegistrationForm,PBBuildForm,PBAddHostForm
from flask_login import login_user, current_user, logout_user, login_required
from webaccessbuild.models import User,PB,RegisteredNode
import random
import os
import os.path
from os import path
import pathlib
from pathlib import Path
import subprocess
import paramiko



#Paramiko Global Connect
global client
client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy)

#Main Home
@app.route('/')
def mainhome():

    return render_template('mainhome.html',title='VXL WAB')

#PB Home
@app.route('/pb_home')
def pb_home():
    pb_pkg_count = len(db.session.query(PB).all())
    pb_page = request.args.get('page',1,type=int)
    pb_package = PB.query.order_by(PB.pb_date_posted.desc()).paginate(page=pb_page,per_page=4)

    return render_template('pb_home.html',title='Package Builder',pb_pkg_count=pb_pkg_count,pb_package=pb_package)


#PB Add Remote Host Node
@app.route('/pb_addremotenode',methods=['POST','GET'])
@login_required
def pb_addhostnode():
    form = PBAddHostForm()

    with open('/root/.ssh/id_rsa.pub',"r") as f:
        publickey_content = f.read()

    if form.validate_on_submit():
        try:
            client.connect(str(form.pb_remote_host_ip.data),timeout=3)
            stdin, stdout, stderr = client.exec_command("hostname")
            cmd_hostname = stdout.read()
            print(cmd_hostname)

            try:
                reg_host = RegisteredNode(ipaddress=str(form.pb_remote_host_ip.data),hostname=cmd_hostname.decode('utf-8').rstrip('\n'),register_host_node=current_user)
                db.session.add(reg_host)
                db.session.commit()
            except Exception as ee:
                print(ee)
                flash(f"Remote Host Machine already Registered !",'info')

        except Exception as ee:
            flash(f"Connection Timeout",'danger')

        flash(f"Remote Host Machine added successfully",'success')
        return redirect(url_for('pb_reghostnode'))

    return render_template('pb_addhost.html',title='Add Remote Node',form=form,publickey_content=publickey_content)

#PB Remote Host Node
@app.route('/pb_reghostnode')
@login_required
def pb_reghostnode():
    page = request.args.get('page',1,type=int)
    regs_host_count = db.session.query(RegisteredNode).count()
    regs_hosts = RegisteredNode.query.paginate(page=page,per_page=4)
    #Check the status of the Remote Host machines
    host_ip_status = []
    for i in db.session.query(RegisteredNode).all():
        try:
            client.connect(str(i),timeout=2)
            stdin, stdout, stderr = client.exec_command("hostname")
            if stdout.channel.recv_exit_status() != 0:
                host_ip_status.append('Down')
            else:
                host_ip_status.append('Running')
        except Exception as ee:
            print(ee)

    return render_template('pb_reghostnode.html',title='Register Host Node',regs_host_count=regs_host_count,regs_hosts=regs_hosts,host_ip_status=host_ip_status)


#PB New PB
@app.route('/pb_newbuild',methods=['GET','POST'])
@login_required
def pb_newbuild():
    form = PBBuildForm()
    
    #PB WorkArea
    pb_pkgbuildid = random.randint(1111,9999)
    pb_pkgbuildpath = '/var/www/html/Packages/'
    
    #Remove Builds which are not finished
    if not len(os.listdir(pb_pkgbuildpath)) == 0:
        for f in os.listdir(pb_pkgbuildpath):
            file = pathlib.Path(pb_pkgbuildpath+f+"/finish.true")
            cmd = "rm -Rf "+pb_pkgbuildpath+str(f)
            proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            o,e = proc.communicate()

    if form.validate_on_submit():

        #Create working directory
        os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data))
        os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0])

        #Check Remote Host is Still Alive
        try:
            client.connect(str(form.remote_host_ip.data),timeout=10)
            stdin,stdout,stderr = client.exec_command("ls "+form.pb_rawpkgpath.data)
            if stdout.channel.recv_exit_status() != 0:
                flash(f"Please Check the remote host path",'danger')
        except Exception as ee:
            flash(f"Connection Timeout.Check Remote Host",'danger')

        #Create the Squashfs File
        stdin,stdout,stderr = client.exec_command("mksquashfs "+form.pb_rawpkgpath.data+" "+form.pb_rawpkgpath.data+"/"+str(form.pb_pkgname.data).casefold().split(':')[1]+".sq"+" "+"-e "+str(form.pb_pkgname.data).casefold().split(':')[1]+".sq")
        #Download the newly created squashfs file
        ftp_client = client.open_sftp()
        ftp_client.get(form.pb_rawpkgpath.data+"/"+str(form.pb_pkgname.data).casefold().split(':')[1]+".sq",pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0]+'/'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq')

        #Get MD5SUM
        cmd_md5sum = "md5sum "+pb_pkgbuildpath+'/'+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0]+'/'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'
        proc = subprocess.Popen(cmd_md5sum,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        o,e = proc.communicate()

        #Remove sq after download
        stdin,stdout,stderr = client.exec_command("rm -rf  "+form.pb_rawpkgpath.data+"/"+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq')

        if form.pb_needpatch.data != True:
            #Update the Database
            pb_update = PB(pb_buildid=str(form.pb_pkgbuildid.data),pb_pkgname=str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq',pb_description=form.pb_pkgdescription.data,pb_os_arch=form.pb_osarch.data,pb_md5sum_pkg=o.decode('utf-8').split(' ')[0],pb_author=current_user)
            db.session.add(pb_update)
            db.session.commit()
        
            return redirect(url_for('pb_home'))
        else:
            
            #Create Firmware Patch work directory
            os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update')

            #Check if it is a Legacy Patch
            if form.pb_patchlegacy.data != True:
               os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update/root/firmware_update/add-pkg')
               os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update/root/firmware_update/delete-pkg')
            else:
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update/root/')
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update/sda1/data/firmware_update/add-pkg')
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Firmware_Update/sda1/data/firmware_update/delete-pkg')

            #Check if remove package list and install script is empty    
            if len(form.pb_removepkg.data) == 0 and len(form.pb_install_script.data) == 0:
                flash(f"Invalid Patch format")
                return redirect(url_for('pb_home'))

                

            flash(f"Package Build Successfully",'success')
            return redirect(url_for('pb_home'))


    return render_template('pb_newbuild.html',title='New Package Build',form=form,build=pb_pkgbuildid)

#User Login Page
@app.route('/login',methods=['GET','POST'])
def user_login():
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user and bcrypt.check_password_hash(user.password,form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('mainhome'))
        else:
            flash('Login Unsuccessful. Please check email or password','danger')

    return render_template('user_login.html',title='Login',form=form)



#User Register Page
@app.route('/register',methods=['GET','POST'])
def user_register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password,password_decrypted=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'Your Account has been created! You are now able to login','success')
        return redirect(url_for('user_login'))
    return render_template('user_register.html',title='Register',form=form)

#User Logout
@app.route('/logout')
def user_logout():
    logout_user()
    return redirect(url_for('mainhome'))