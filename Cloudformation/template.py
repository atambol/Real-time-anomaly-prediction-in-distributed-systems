import troposphere.ec2 as ec2
import troposphere.cloudformation as cfn
import troposphere.autoscaling as autoscaling
from troposphere.policies import CreationPolicy, ResourceSignal
from troposphere import Parameter, Template, Tags, Ref, Join, Base64
import socket
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--keyname', '-k', help='name of the key for accessing the stack', default="724_keypair")
parser.add_argument('--id', '-i', help='unique time stamp id', default=None, required=False)
args = parser.parse_args()

# Vars
keyname = args.keyname
epoch_time = args.id
template_file = "_".join([epoch_time, "template.json"])
hostname = socket.gethostname()
region = 'us-east-2'
availability_zone = region + 'b'
description = "724 stack created by {} at {}".format(hostname, epoch_time)
address = {
    "vpc_cidr": '172.25.0.0/16',
    "public_subnet_cidr": '172.25.0.0/17',
    "private_subnet_cidr": '172.25.128.0/17',
    "nat": '172.25.0.5/32',
    "kafka": "172.25.129.5/32",
    "rubis": "172.25.130.5/32"
}

ami_ids = {
    "nat": "ami-f27b5a97",
    "rubis": "ami-d90c57bc",
    "kafka": "ami-d90c57bc",
    "spark": "ami-d90c57bc"
}

t = Template()
t.add_version("2010-09-09")
t.add_description(description)


vpc_cidr = t.add_parameter(Parameter(
    'VPCCIDR',
    Default=address['vpc_cidr'],
    Description='The IP address space for this VPC, in CIDR notation',
    Type='String',
))

public_subnet_cidr = t.add_parameter(Parameter(
    'PublicSubnetCidr',
    Type='String',
    Description='Public Subnet CIDR',
    Default=address['public_subnet_cidr']
))

private_subnet_cidr = t.add_parameter(Parameter(
    'PrivateSubnetCidr',
    Type='String',
    Description='Public Subnet CIDR',
    Default=address['private_subnet_cidr']
))

vpc = t.add_resource(ec2.VPC(
    "VPC",
    CidrBlock=Ref(vpc_cidr),
    InstanceTenancy="default",
    Tags=Tags(
        Name=Ref("AWS::StackName"),
        Creator=hostname
    )
))

public_subnet = t.add_resource(ec2.Subnet(
    'PublicSubnet',
    CidrBlock=Ref(public_subnet_cidr),
    MapPublicIpOnLaunch=True,
    AvailabilityZone=availability_zone,
    VpcId=Ref(vpc),
))

private_subnet = t.add_resource(ec2.Subnet(
    'PrivateSubnet',
    CidrBlock=Ref(private_subnet_cidr),
    MapPublicIpOnLaunch=False,
    AvailabilityZone=availability_zone,
    VpcId=Ref(vpc),
))

igw = t.add_resource(ec2.InternetGateway(
    "InternetGateway",
    Tags=Tags(
        Name=Join("_", [Ref("AWS::StackName"), "gateway"]),
      )
))

igw_vpc_attachment = t.add_resource(ec2.VPCGatewayAttachment(
    "InternetGatewayAttachment",
    InternetGatewayId=Ref(igw),
    VpcId=Ref(vpc)
))

public_route_table = t.add_resource(ec2.RouteTable(
    "PublicRouteTable",
    VpcId=Ref(vpc),
    Tags=Tags(
        Name=Join("_", [Ref("AWS::StackName"), "public", "route", "table"])
    )
))

public_route_association = t.add_resource(ec2.SubnetRouteTableAssociation(
    'PublicRouteAssociation',
    SubnetId=Ref(public_subnet),
    RouteTableId=Ref(public_route_table),
))

default_public_route = t.add_resource(ec2.Route(
    'PublicDefaultRoute',
    RouteTableId=Ref(public_route_table),
    DestinationCidrBlock='0.0.0.0/0',
    GatewayId=Ref(igw),
))

private_route_table = t.add_resource(ec2.RouteTable(
    'PrivateRouteTable',
    VpcId=Ref(vpc),
    Tags=Tags(
        Name=Join("_", [Ref("AWS::StackName"), "private", "route", "table"])
    )
))

private_route_association = t.add_resource(ec2.SubnetRouteTableAssociation(
    'PrivateRouteAssociation',
    SubnetId=Ref(private_subnet),
    RouteTableId=Ref(private_route_table),
))

nat_security_group = t.add_resource(ec2.SecurityGroup(
    'NatSecurityGroup',
    GroupDescription='Nat security group',
    VpcId=Ref(vpc),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol='-1',
            FromPort=-1,
            ToPort=-1,
            CidrIp='0.0.0.0/0'
        )
    ],
    SecurityGroupEgress=[
        ec2.SecurityGroupRule(
            IpProtocol='-1',
            FromPort=-1,
            ToPort=-1,
            CidrIp='0.0.0.0/0'
        )
    ]
))

nat_instance_metadata = autoscaling.Metadata(
    cfn.Init({
        'config': cfn.InitConfig(
            packages={'yum': {'httpd': []}},
            files=cfn.InitFiles({
                '/etc/cfn/cfn-hup.conf': cfn.InitFile(
                    content=Join('',
                        ['[main]\n',
                         'stack=',
                         Ref('AWS::StackName'),
                         '\n',
                         'region=',
                         Ref('AWS::Region'),
                         '\n',
                        ]),
                    mode='000400',
                    owner='root',
                    group='root'),
                '/etc/cfn/hooks.d/cfn-auto-reloader.conf': cfn.InitFile(
                    content=Join('',
                        ['[cfn-auto-reloader-hook]\n',
                         'triggers=post.update\n',
                         'path=Resources.NatInstance.Metadata.AWS::CloudFormation::Init\n',
                         'action=/opt/aws/bin/cfn-init -v ',
                         '         --stack=',
                         Ref('AWS::StackName'),
                         '         --resource=NatInstance',
                         '         --region=',
                         Ref('AWS::Region'),
                         '\n',
                         'runas=root\n',
                        ]))}),
            services={
                'sysvinit': cfn.InitServices({
                    'httpd': cfn.InitService(
                        enabled=True,
                        ensureRunning=True),
                    'cfn-hup': cfn.InitService(
                        enabled=True,
                        ensureRunning=True,
                        files=[
                            '/etc/cfn/cfn-hup.conf',
                            '/etc/cfn/hooks.d/cfn-auto-reloader.conf'
                        ])})})}))

nat_instance = t.add_resource(ec2.Instance(
    'NatInstance',
    ImageId=ami_ids["nat"],
    InstanceType="t2.micro",
    Metadata=nat_instance_metadata,
    KeyName=keyname,
    SourceDestCheck='false',
    IamInstanceProfile='NatS3Access',
    NetworkInterfaces=[
        ec2.NetworkInterfaceProperty(
            GroupSet=[Ref(nat_security_group)],
            AssociatePublicIpAddress='true',
            DeviceIndex='0',
            DeleteOnTermination='true',
            SubnetId=Ref(public_subnet))],
    UserData=Base64(
        Join(
            '',
            [
                '#!/bin/bash -xe\n',
                'yum update -y aws-cfn-bootstrap\n',
                'aws --region ', Ref('AWS::Region'), ' s3 cp s3://atambol/724_keypair.pem /home/ec2-user/.ssh/724_keypair.pem\n',
                'chmod 400 /home/ec2-user/.ssh/724_keypair.pem\n',
                'chown ec2-user.ec2-user /home/ec2-user/.ssh/724_keypair.pem\n',

                "# Configure iptables\n",
                "/sbin/iptables -t nat -A POSTROUTING -o eth0 -s 0.0.0.0/0 -j MASQUERADE\n",
                "/sbin/iptables-save > /etc/sysconfig/iptables\n",
                "# Configure ip forwarding and redirects\n",
                "echo 1 >  /proc/sys/net/ipv4/ip_forward && echo 0 >  /proc/sys/net/ipv4/conf/eth0/send_redirects\n",
                "mkdir -p /etc/sysctl.d/\n",
                "cat <<EOF > /etc/sysctl.d/nat.conf\n",
                "net.ipv4.ip_forward = 1\n",
                "net.ipv4.conf.eth0.send_redirects = 0\n",
                "EOF\n",
                "sysctl -p /etc/sysctl.d/nat.conf\n",

                '/opt/aws/bin/cfn-init -v ',
                '         --stack=',
                Ref('AWS::StackName'),
                '         --resource=NatInstance',
                '         --region=',
                Ref('AWS::Region'),
                '\n',
                '/opt/aws/bin/cfn-signal -e $?',
                '         --stack=',
                Ref('AWS::StackName'),
                '         --resource=NatInstance',
                '         --region=',
                Ref('AWS::Region'),
                '\n',
            ])),
    CreationPolicy=CreationPolicy(
        ResourceSignal=ResourceSignal(
            Count=1,
            Timeout='PT15M')),
    DependsOn=["InternetGatewayAttachment"],
    Tags=Tags(
        Name=Join("_", [Ref("AWS::StackName"), "Nat"]))
))
#
# eip = t.add_resource(ec2.EIP(
#     'NatEip',
#     DependsOn='InternetGatewayAttachment',
#     InstanceId=Ref(nat_instance)
# ))

default_private_route = t.add_resource(ec2.Route(
    'PrivateDefaultRoute',
    RouteTableId=Ref(private_route_table),
    DestinationCidrBlock='0.0.0.0/0',
    InstanceId=Ref(nat_instance),
    DependsOn=["NatInstance"],
))

instance_security_group = t.add_resource(ec2.SecurityGroup(
    'InstanceSecurityGroup',
    GroupDescription='Instance security group',
    VpcId=Ref(vpc),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol='-1',
            FromPort=-1,
            ToPort=-1,
            CidrIp='0.0.0.0/0'
        )
    ],
    SecurityGroupEgress=[
        ec2.SecurityGroupRule(
            IpProtocol='-1',
            FromPort=-1,
            ToPort=-1,
            CidrIp='0.0.0.0/0'
        )
    ]
))


def get_instance_metadata(instance_name):
    return autoscaling.Metadata(
        cfn.Init({
            'config': cfn.InitConfig(
                packages={'yum': {'httpd': []}},
                files=cfn.InitFiles({
                    '/etc/cfn/cfn-hup.conf': cfn.InitFile(
                        content=Join('',
                            ['[main]\n',
                             'stack=',
                             Ref('AWS::StackName'),
                             '\n',
                             'region=',
                             Ref('AWS::Region'),
                             '\n',
                            ]),
                        mode='000400',
                        owner='root',
                        group='root'),
                    '/etc/cfn/hooks.d/cfn-auto-reloader.conf': cfn.InitFile(
                        content=Join('',
                            ['[cfn-auto-reloader-hook]\n',
                             'triggers=post.update\n',
                             'path=Resources.',
                             instance_name,
                             '.Metadata.AWS::CloudFormation::Init\n',
                             'action=/opt/aws/bin/cfn-init -v ',
                             '         --stack=',
                             Ref('AWS::StackName'),
                             '         --resource=',
                             instance_name,
                             '         --region=',
                             Ref('AWS::Region'),
                             '\n',
                             'runas=root\n',
                            ]))}),
                services={
                    'sysvinit': cfn.InitServices({
                        'httpd': cfn.InitService(
                            enabled=True,
                            ensureRunning=True),
                        'cfn-hup': cfn.InitService(
                            enabled=True,
                            ensureRunning=True,
                            files=[
                                '/etc/cfn/cfn-hup.conf',
                                '/etc/cfn/hooks.d/cfn-auto-reloader.conf'
                            ])})})}))


rubis_instance = t.add_resource(ec2.Instance(
    'RubisInstance',
    ImageId=ami_ids["rubis"],
    InstanceType="t2.micro",
    Metadata=get_instance_metadata("RubisInstance"),
    KeyName=keyname,
    SourceDestCheck='true',
    NetworkInterfaces=[
        ec2.NetworkInterfaceProperty(
            GroupSet=[Ref(instance_security_group)],
            AssociatePublicIpAddress='false',
            DeviceIndex='0',
            DeleteOnTermination='true',
            SubnetId=Ref(private_subnet))],
    UserData=Base64(
        Join(
            '',
            [
                '#!/bin/bash -xe\n',
                'yum update -y aws-cfn-bootstrap\n',
                '/opt/aws/bin/cfn-init -v ',
                '         --stack=',
                Ref('AWS::StackName'),
                '         --resource=RubisInstance ',
                '         --region=',
                Ref('AWS::Region'),
                '\n',
                '/opt/aws/bin/cfn-signal -e $? ',
                '         --stack=',
                Ref('AWS::StackName'),
                '         --resource=RubisInstance ',
                '         --region=',
                Ref('AWS::Region'),
                '\n',
            ])),
    CreationPolicy=CreationPolicy(
        ResourceSignal=ResourceSignal(
            Count=1,
            Timeout='PT15M')),
    DependsOn=["PrivateDefaultRoute"],
    Tags=Tags(
        Name=Join("_", [Ref("AWS::StackName"), "Rubis"]))
))

# Generate a template
with open(template_file, "w") as f:
    f.writelines(t.to_json())
