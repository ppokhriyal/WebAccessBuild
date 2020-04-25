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
import tarfile


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

        #Check Patch check box is checked or not
        if form.pb_needpatch.data == True:
            #Check for Current patch or Legacy patch format

            if form.pb_patchtype.data == "Current Patch":
                #Create current patch working area
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/add-pkg')
                #copy the new build package
                cmd = "cp -pa "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0]+'/'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'+" "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/add-pkg/'+str(form.pb_pkgname.data).casefold().split(':')[0]+':'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

                #Check for remove packages and files
                if len(form.pb_removepkg.data) != 0:

                    remove_pkgs = form.pb_removepkg.data.split(':')

                    try:
                        for i in remove_pkgs:
                            #Check for prefix
                            prefix = i.split('-',1)

                            if prefix[0].casefold() not in ['core','basic','apps']:
                                flash(f'Missing Prefix in {prefix[0]},while removing package','danger')
                                return redirect(url_for('pb_home'))

                            os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg')    

                            if prefix[0].casefold() == 'core':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/core:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'basic':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/basic:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'apps':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/apps:'+prefix[1]).touch()

                    except Exception as ee:
                        print(ee)

                #Check if Install script is empty
                if len(form.pb_install_script.data) != 0:

                    os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root')

                    install_script = form.pb_install_script.data.split(' ')
                    f = open(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/install',"a+")
                    f.write("#!/bin/bash\n")
                    for i in " ".join(install_script):
                        f.write(i)

                    f.close()

                    #Create findminmax.sh
                    with open(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/findminmax.sh',"a") as f:
                        f.write('#!/bin/bash')
                        f.write('\n')
                        f.write('mount -o remount,rw /sda1')
                        f.write('\n')
                        f.write('exit 0')

                    #Remove ^M from install script
                    subprocess.call(["sed -i -e 's/\r//g' "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/Patch/root/install"],shell=True)
                    subprocess.call(["sed -i -e 's/\r//g' "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/Patch/root/findminmax.sh"],shell=True)

                #CHMOD
                subprocess.call(["chmod -R 755 "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)],shell=True)

                #Build Final Patch Tar
                patch_name = form.pb_pkgname.data.split(':')[1]+'.tar.bz2'
                tar_file_path = pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name
                tar = tarfile.open(tar_file_path,mode='w:bz2')
                os.chdir(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/')
                tar.add(".")
                tar.close()
                



            else:
                #Legacy patch selected
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/add-pkg')
        else:
            #Patch Checkbox is not checked
            pass


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