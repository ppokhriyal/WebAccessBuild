from flask import render_template, url_for, flash, redirect, request, abort, session
from webaccessbuild import app, db, bcrypt
from webaccessbuild.forms import LoginForm,RegistrationForm,PBBuildForm,PBAddHostForm,FBBuildForm
from flask_login import login_user, current_user, logout_user, login_required
from webaccessbuild.models import User,PB,RegisteredNode,FB
import random
import os
import os.path
from os import path
import pathlib
from pathlib import Path
import subprocess
import paramiko
import tarfile
import urllib3
import wget
import requests

#Paramiko Global Connect
global client
client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy)

#Main Home
@app.route('/')
def mainhome():

    pb_count = len(db.session.query(PB).all())
    fb_count = len(db.session.query(FB).all())
    return render_template('mainhome.html',title='VXL WAB',pb_count=pb_count,fb_count=fb_count)

#PB Home
@app.route('/pb_home')
def pb_home():
    pb_pkg_count = len(db.session.query(PB).all())
    pb_page = request.args.get('page',1,type=int)
    pb_package = PB.query.order_by(PB.pb_date_posted.desc()).paginate(page=pb_page,per_page=4)

    return render_template('pb_home.html',title='Package Builder',pb_pkg_count=pb_pkg_count,pb_package=pb_package,pb_page=pb_page)


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
            if not file.exists():
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
        pb_pkg_md5sum = o.decode('utf-8').split(' ')[0]

        #Remove sq after download
        stdin,stdout,stderr = client.exec_command("rm -rf  "+form.pb_rawpkgpath.data+"/"+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq')

        #Check Patch check box is checked or not
        if form.pb_needpatch.data == True:
            #Check for Current patch or Legacy patch format

            if form.pb_patchtype.data == "Current Patch":
                #Create current patch working area
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/add-pkg')
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root')

                #Create default findminmax script
                #Create findminmax.sh
                with open(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/findminmax.sh',"a") as f:
                    f.write('#!/bin/bash')
                    f.write('\n')
                    f.write('mount -o remount,rw /sda1')
                    f.write('\n')
                    f.write('exit 0')

                #Remove ^M from install script
                subprocess.call(["sed -i -e 's/\r//g' "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/Patch/root/findminmax.sh"],shell=True)

                #copy the new build package
                cmd = "cp -pa "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0]+'/'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'+" "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/add-pkg/'+str(form.pb_pkgname.data).casefold().split(':')[0]+':'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

                #Check for remove packages and files
                if len(form.pb_removepkg.data) != 0:

                    os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg')
                    remove_pkgs = form.pb_removepkg.data.split(':')

                    try:
                        for i in remove_pkgs:
                            #Check for prefix
                            prefix = i.split('-',1)

                            if prefix[0].casefold() not in ['core','basic','apps','boot','data','root']:
                                flash(f'Missing Prefix in {prefix[0]},while removing package','danger')
                                return redirect(url_for('pb_home'))

                            if prefix[0].casefold() == 'core':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/core:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'basic':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/basic:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'apps':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/apps:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'boot':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/boot:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'data':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/data:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'root':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/sda1/data/firmware_update/delete-pkg/root:'+prefix[1]).touch()

                    except Exception as ee:
                        print(ee)

                #Check if Install script is not empty
                if len(form.pb_install_script.data) != 0:

                    install_script = form.pb_install_script.data.split(' ')
                    f = open(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/install',"a+")
                    f.write("#!/bin/bash\n")
                    for i in " ".join(install_script):
                        f.write(i)

                    f.close()

                    #Remove ^M from install script
                    subprocess.call(["sed -i -e 's/\r//g' "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/Patch/root/install"],shell=True)

                #CHMOD
                subprocess.call(["chmod -R 755 "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)],shell=True)

                #Build Final Patch Tar
                patch_name = str(form.pb_pkgbuildid.data)+'_'+form.pb_patchname.data.replace(' ','_')+'.tar.bz2'
                tar_file_path = pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name
                tar = tarfile.open(tar_file_path,mode='w:bz2')
                os.chdir(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/')
                tar.add(".")
                tar.close()
                
                #Damage Patch
                cmd = "damage corrupt "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name+" 1"
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

                #MD5SUM of Patch
                cmd = "md5sum "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()
                pb_patch_md5sum = o.decode('utf-8').split(' ')[0]

                #Update DataBase
                update_db = PB(pb_buildid=form.pb_pkgbuildid.data,pb_pkgname=form.pb_pkgname.data.split(':')[1],pb_patchname=str(form.pb_pkgbuildid.data)+'_'+form.pb_patchname.data.replace(' ','_'),pb_description=form.pb_pkgdescription.data,
                    pb_os_arch=form.pb_osarch.data,pb_md5sum_pkg=pb_pkg_md5sum,pb_md5sum_patch=pb_patch_md5sum,pb_author=current_user)
                db.session.add(update_db)
                db.session.commit()

                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/"+"finish.true").touch()
                flash(f"Package {form.pb_pkgname.data} created successfully",'success')
                return redirect(url_for('pb_home'))

            else:
                #Legacy patch selected
                os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/add-pkg')
                
                #copy the new build package
                cmd = "cp -pa "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/'+str(form.pb_osarch.data)+'/'+str(form.pb_pkgname.data).casefold().split(':')[0]+'/'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'+" "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/add-pkg/'+str(form.pb_pkgname.data).casefold().split(':')[0]+':'+str(form.pb_pkgname.data).casefold().split(':')[1]+'.sq'
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

                #Check for remove packages and files
                if len(form.pb_removepkg.data) != 0:

                    os.makedirs(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg')
                    remove_pkgs = form.pb_removepkg.data.split(':')
                    try:
                        for i in remove_pkgs:
                            #Check for prefix
                            prefix = i.split('-',1)
                            if prefix[0].casefold() not in ['core','basic','apps','boot','data','root']:
                                flash(f'Missing Prefix in {prefix[0]},while removing package','danger')
                                return redirect(url_for('pb_home'))

                            if prefix[0].casefold() == 'core':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/core:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'basic':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/basic:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'apps':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/apps:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'boot':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/boot:'+prefix[1]).touch()

                            if prefix[0].casefold() == 'data':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/data:'+prefix[1]).touch()
    
                            if prefix[0].casefold() == 'root':
                                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/root/firmware_update/delete-pkg/root:'+prefix[1]).touch()

                    except Exception as ee:
                        print(ee)

                #Check if Install script is empty
                if len(form.pb_install_script.data) != 0:

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

                #CHMOD
                subprocess.call(["chmod -R 755 "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)],shell=True)

                #Build Final Patch Tar
                patch_name = str(form.pb_pkgbuildid.data)+'_'+form.pb_patchname.data.replace(' ','_')+'.tar.bz2'
                tar_file_path = pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name
                tar = tarfile.open(tar_file_path,mode='w:bz2')
                os.chdir(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/')
                tar.add(".")
                tar.close()
                
                #Damage Patch
                cmd = "damage corrupt "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name+" 1"
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

                #MD5SUM of Patch
                cmd = "md5sum "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+'/Patch/'+patch_name
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()
                pb_patch_md5sum = o.decode('utf-8').split(' ')[0]

                #Update DataBase
                update_db = PB(pb_buildid=form.pb_pkgbuildid.data,pb_pkgname=form.pb_pkgname.data.split(':')[1],pb_patchname=str(form.pb_pkgbuildid.data)+'_'+form.pb_patchname.data.replace(' ','_'),pb_description=form.pb_pkgdescription.data,
                    pb_os_arch=form.pb_osarch.data,pb_md5sum_pkg=pb_pkg_md5sum,pb_md5sum_patch=pb_patch_md5sum,pb_author=current_user)
                db.session.add(update_db)
                db.session.commit()

                Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/"+"finish.true").touch()
                flash(f"Package {form.pb_pkgname.data} created successfully",'success')
                return redirect(url_for('pb_home'))
    
        else:
            #Patch Checkbox is not checked
            subprocess.call(["chmod -R 755 "+pb_pkgbuildpath+str(form.pb_pkgbuildid.data)],shell=True)
            
            #Update DataBase
            update_db = PB(pb_buildid=form.pb_pkgbuildid.data,pb_pkgname=form.pb_pkgname.data.split(':')[1],pb_patchname='None',pb_description=form.pb_pkgdescription.data,
                    pb_os_arch=form.pb_osarch.data,pb_md5sum_pkg=pb_pkg_md5sum,pb_md5sum_patch='None',pb_author=current_user)
            db.session.add(update_db)
            db.session.commit()

            Path(pb_pkgbuildpath+str(form.pb_pkgbuildid.data)+"/"+"finish.true").touch()
            flash(f"Package {form.pb_pkgname.data} created successfully",'success')
            return redirect(url_for('pb_home'))

    return render_template('pb_newbuild.html',title='New Package Build',form=form,build=pb_pkgbuildid)

#Remove Packages
@app.route('/pb_home/pb_delete/<int:pb_id>')
@login_required
def pb_delete(pb_id):

    pb_info = PB.query.get_or_404(pb_id)

    if pb_info.pb_author != current_user:
        abort(403)

    db.session.delete(pb_info)
    db.session.commit()

    cmd = "rm -Rf /var/www/html/Packages/"+str(pb_info.pb_buildid)
    proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    o,e = proc.communicate()
    flash('Package Build information deleted successfully','success')
    return redirect(url_for('pb_home'))

#####Firmware Update Patch#####
#FB Home
@app.route('/fb_home',methods=['GET','POST'])
def fb_home():
    page = request.args.get('page',1,type=int)
    fb = FB.query.filter_by(fb_author=current_user).order_by(FB.fb_date_posted.desc()).paginate(page=page,per_page=4)
    fb_count = len(db.session.query(FB).all())

    return render_template('fb_home.html',title='Firmware Update Patch',fb=fb,fb_count=fb_count)


#FB New Build
@app.route('/fb_newbuild',methods=['GET','POST'])
@login_required
def fb_newbuild():
    form = FBBuildForm()
    
    #FB WorkArea
    fbbuildid = random.randint(1111,9999)
    fbbuildpath = '/var/www/html/Firmware/'

    #Remove FB which are not finished
    if not len(os.listdir(fbbuildpath)) == 0:
        for f in os.listdir(fbbuildpath):
            file = pathlib.Path(fbbuildpath+f+"/finish.true")
            if not file.exists():
                cmd = "rm -Rf "+fbbuildpath+str(f)
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                o,e = proc.communicate()

    if form.validate_on_submit():

        #Create FB Working Directory
        os.makedirs(fbbuildpath+str(form.fb_buildid.data))
        os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data)

        #Check for Firmware Mode
        if form.fb_type.data == "Current Patch":

            #Build Current Patch work area template
            os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/')
            os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/')

            #Check if Add and Remove both are empty
            if len(form.fb_add.data) == 0 and len(form.fb_remove.data) == 0:
                flash(f"Both Add and Remove Files and Packages cannot be empty",'danger')

            #Check if Add Files and Packages are not empty
            if len(form.fb_add.data) != 0:
                os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/')
                add_pkgs = form.fb_add.data.split(';')

                for i in add_pkgs:

                    #Check for Prefix
                    prefix = i.split('-',1)

                    if prefix[0].casefold() not in ['core','basic','apps','boot','data','root']:
                        flash(f'Missing Prefix in {prefix[0]},while adding package','danger')

                    #Check URL Status
                    try:
                        url_status =  requests.head(prefix[1])
                        if url_status.status_code == 200:
                            
                            pkgname = prefix[1].split('/')[::-1]

                            if prefix[0].casefold() == 'core':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/core:'+pkgname[0])

                            if prefix[0].casefold() == 'basic':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/basic:'+pkgname[0])

                            if prefix[0].casefold() == 'apps':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/apps:'+pkgname[0])
                                
                            if prefix[0].casefold() == 'boot':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/boot:'+pkgname[0])
                                
                            if prefix[0].casefold() == 'data':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/data:'+pkgname[0])
                                
                            if prefix[0].casefold() == 'root':
                                wget.download(url=prefix[1],out=fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/add-pkg/root:'+pkgname[0])                    
                        else:
                            flash(f'Invalid URL : {prefix[1]}','danger')
                            return redirect(url_for('fb_home'))
                    except Exception as ee :
                        flash(f'Invalid URL : {prefix[1]}','danger')
                        return redirect(url_for('fb_home'))

            #Check for Remove files and Packages
            if len(form.fb_remove.data) != 0:

                os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/')
                remove_pkgs = form.fb_remove.data.split(';')

                for i in remove_pkgs:

                    #Check Prefix
                    prefix = i.split('-',1)

                    if prefix[0].casefold() not in ['core','basic','apps','boot','data','root']:
                        flash(f'Missing Prefix in {prefix[0]},while removing package','danger')
                        return redirect(url_for('fb_home'))

                    if prefix[0].casefold() == 'core':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'boot:'+prefix[1]).touch()

                    if prefix[0].casefold() == 'basic':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'basic:'+prefix[1]).touch()

                    if prefix[0].casefold() == 'apps':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'apps:'+prefix[1]).touch()

                    if prefix[0].casefold() == 'boot':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'boot:'+prefix[1]).touch()

                    if prefix[0].casefold() == 'data':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'data:'+prefix[1]).touch()

                    if prefix[0].casefold() == 'root':
                        Path(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/sda1/data/firmware_update/delete-pkg/'+'root:'+prefix[1]).touch()    

            #Check for MinMax
            if form.fb_min_img_build.data == 1 and form.fb_max_img_build.data == 1:
                #skip findminmax and create default script
                with open(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/findminmax.sh',"a") as f:
                    f.write("#!/bin/bash")
                    f.write('\n\n')
                    f.write("mount -o remount,rw /sda1")
                    f.write('\n')
                    f.write("exit 0")
                #Remove ^M
                subprocess.call(["sed -i -e 's/\r//g' /var/www/html/Firmware/"+str(form.fb_buildid.data)+form.fb_osarch.data+"/template/root/findminmax.sh"],shell=True)

            elif form.fb_min_img_build.data > form.fb_max_img_build.data :
                flash(f"Minimum Build cannot be greater than Maximum Build",'danger')
                return redirect(url_for('fb_home'))
            else:

                #Total size of packages to be added
                cmd = "du -schBM "+fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+"/template/sda1/data/firmware_update/add-pkg/* | tail -n1 | awk -F' ' '{print $1}'"
                proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                e,o = proc.communicate()
                print(e)
                print(o)
                add_pkg_size = e.decode('utf8').rstrip('\n')

                #Start writing FindMinMax Script
                f = open(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/findminmax',"x")
                f.write(f"""#!/bin/bash\n\n
mount -o remount,rw /sda1\n
#Check for OS-Arch
os_arch_type = `file /usr/verixo-bin/OS_Desktop`
echo $os_arch_type | grep -i "ELF 32-bit LSB executable"
status=$?

if [ $status -eq 0 ]
then
    os_arch_type=32
else
    os_arch_type=64
fi

if [ {form.fb_osarch.data} == "Multi-Arch" ]
then
    echo "It's a Multi-Arch Patch"
else
    if [ {form.fb_osarch.data} -ne "$os_arch_type" ]
    then
        exit 1
    fi
fi

#Check Min/Max value
/usr/verixo-bin/verify-patch.sh {form.fb_min_img_build.data} {form.fb_max_img_build.data}
status=$?

if [ $status -ne 0 ]
then
    exit 1
fi

#Check for Update Build
if [ -f /sda1/data/firmware_update/add-pkg/basic:verixo-bin.sq ]
then
    mkdir /opt/demoloop
    mount -o loop /sda1/data/firmware_update/add-pkg/basic:verixo-bin.sq /opt/demoloop/
    build=`cat /opt/demoloop/usr/verixo-bin/.updatebuild
    umount /opt/demoloop
    rm -rf /opt/demoloop

    /usr/verixo-bin/Firmwareupdate --checkupdatebuild $build
    status=$?
    if [ $status -ne 0 ]
    then
        exit 1
    fi
fi

#Available Space left for Package to be added
/usr/verixo-bin/Firmwareupdate --checksize {add_pkg_size}
status=$?
if [ $status -ne 0 ]
then
    exit 1
fi

#All Good
exit 0
    
""")

                f.close()

            #Writing Install Script
            if len(form.fb_install_script.data) !=0 :

                install_script = form.fb_install_script.data.split(' ')
                f = open(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/install',"a+")
                f.write("#!/bin/bash\n")
                for i in " ".join(install_script):
                    f.write(i)

                f.close()

                #Remove ^M from install script
                subprocess.call(["sed -i -e 's/\r//g' "+fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/install'],shell=True)    

            #CHMOD
            subprocess.call(["chmod -R 755 "+fbbuildpath+str(form.fb_buildid.data)],shell=True)

            #Build Final Patch Tar
            patchname = form.fb_buildid.data+'_'+form.fb_name.data.replace(' ','_')+'.tar.bz2'
            tar_file_path = fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/'+patchname
            tar = tarfile.open(tar_file_path,mode='w:bz2')
            os.chdir(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/')
            tar.add(".")
            tar.close()

            #Damage Patch
            cmd = "damage corrupt "+fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/'+patchname+" 1"
            proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            o,e = proc.communicate()

            #MD5SUM of Patch
            cmd = "md5sum "+fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/'+patchname
            proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            o,e = proc.communicate()
            patch_md5sum = o.decode('utf-8').split(' ')[0]

            #Update DataBase
            update_db = FB(fb_buildid=form.fb_buildid.data,fb_name=patchname,fb_description=form.fb_description.data,fb_os_arch=form.fb_osarch.data,fb_md5sum=patch_md5sum,fb_author=current_user)
            db.session.add(update_db)
            db.session.commit()

            flash(f'Firmware Update Patch created successfully','success')
            return redirect(url_for('fb_home'))

        else:
            
            #Build Legacy Patch work area template
            os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/firmware_update/')
            os.makedirs(fbbuildpath+str(form.fb_buildid.data)+'/'+form.fb_osarch.data+'/template/root/')


    return render_template('fb_newbuild.html',title='Firmware New Build',form=form,build=fbbuildid)

#Remove Firmware
@app.route('/delete_fb/<int:fb_id>')
@login_required
def delete_fb(fb_id):
    fb_info = FB.query.get_or_404(fb_id)
    if fb_info.fb_author != current_user:
         abort(403)

    db.session.delete(fb_info)
    db.session.commit()

    cmd = "rm -Rf /var/www/html/Firmware/"+str(fb_info.fb_buildid)
    proc = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    o,e = proc.communicate()
    flash('Firmware Build information deleted successfully','success')
    return redirect(url_for('fb_home'))

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