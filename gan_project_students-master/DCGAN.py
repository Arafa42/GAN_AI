import torch
import gc
from models import *
from utils import *
from dataset import *
import torch.optim as optim
from torch.autograd import Variable
import wandb
from custom_parser import *
from fid_score import *
import models
import utils

# Load configurations
config = CustomParser().parse({})
config["device"] = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
device = config["device"]
print(device)
print(torch. __version__)
print(f"Is CUDA supported by this system? {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")

# Storing ID of current CUDA device
cuda_id = torch.cuda.current_device()
print(f"ID of current CUDA device:{torch.cuda.current_device()}")

learning_rate = config["learning_rate"]


# manual seeds
torch.manual_seed(config["random_seed"])
torch.cuda.manual_seed(config["random_seed"])

# Ensure save directories exists
create_dir(config["save_path"])
save_config(config)

# Load dataset
dataset = AnimeDataset(config)
denormalize = Denormalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])

# TODO: define the generator and discriminator
# TIP 1: don't forget to apply the weights_init function from utils.py.
# TIP 2: don't forget to put the models on the correct device.
generator = models.Generator(config).to(device)
generator.apply(weights_init)
discriminator = models.Discriminator().to(device)
discriminator.apply(weights_init)

# Weights and biases
if config["wandb"]:
    wandb.init(project="GAN", entity="team_sigma", name=config["name"] + "_train_default")
    wandb.config = {
        "learning_rate": config['learning_rate'],
        "epochs": config['num_epochs'],
        "batch_size": config['batch_size']
    }
    wandb.watch(generator, log='all')
    wandb.watch(discriminator, log='all')
    if config["fid"]:
        block_idx = InceptionV3.BLOCK_INDEX_BY_DIM[2048]
        model = InceptionV3([block_idx]).to(device)

# TODO: define loss function
adversarial_loss = nn.BCELoss()

# TODO: define optimizers

G_optimizer = torch.optim.AdamW(generator.parameters(), lr=config['learning_rate'], betas=(.4, .99), weight_decay=0.00005, eps=1e-8) # PREVIOUS WAS 0.5 -> 0.99
D_optimizer = torch.optim.AdamW(discriminator.parameters(), lr=config['learning_rate'], betas=(.4, .99), weight_decay=0.00005, eps=1e-8) # PREVIOUS WAS 0.5 -> 0.99

# define all ones and all zeros tensors
real_target = Variable(torch.ones(config["batch_size"], 1).to(device))
fake_target = Variable(torch.zeros(config["batch_size"], 1).to(device))

# this fixed noise is for improvement visualisation only
fixed_noise = torch.randn(128, config["latent_dim"], 1, 1, device=device)

# print examples from dataset
for index, (images, _) in enumerate(dataset.train_loader):
    if config["wandb"]:
        wandb_images = wandb.Image(images, caption="Dataset examples")
        wandb.log({"examples": wandb_images})
    else:
        show_images(images, denormalize)
    break

for epoch in range(1, config["num_epochs"] + 1):
    D_loss_list, G_loss_list = [], []

    for index, (real_images, _) in enumerate(dataset.train_loader):
        D_optimizer.zero_grad()

        ## Discriminator real ##
        real_images = real_images.to(device)
        # TODO: forward through discriminator
        output = discriminator.forward(real_images)
        # TODO: calculate loss (use the function from utils.py)
        D_real_loss = utils.discriminator_loss(adversarial_loss, output, real_target)
        # TODO: backpropagate the loss
        D_real_loss.backward()
        ## Discriminator fake ##
        # TODO: create a noise vector of the correct dimensions
        noise_vector = torch.randn(128, config["latent_dim"], 1, 1, device=device)



        # TODO: forward the noise vector through the generator
        generated_image = generator.forward(noise_vector)
        # TODO: forward through the discriminator
        output = discriminator.forward(generated_image.detach())
        # TODO: calculate loss (use the function from utils.py)
        D_fake_loss = utils.discriminator_loss(adversarial_loss, output, fake_target)
        # TODO: backpropagate the loss
        D_fake_loss.backward()
        # TODO: take a step with the optimizer
        D_optimizer.step()

        # Discriminator tot loss
        D_total_loss = D_real_loss + D_fake_loss
        D_loss_list.append(D_total_loss)

        ## Train G on D's output ##
        G_optimizer.zero_grad()
        # TODO: forward generated image through the discriminator
        gen_output = discriminator.forward(generated_image)
        # TODO: calculate loss (use the function from utils.py)

        #G_loss = utils.discriminator_loss(adversarial_loss, gen_output, real_target)
        G_loss = utils.generator_loss(adversarial_loss, gen_output, real_target)

        G_loss_list.append(G_loss)
        # TODO: backpropagate the loss
        G_loss.backward()
        # TODO: take a step with the optimizer
        G_optimizer.step()


    discr_loss_mean = torch.mean(torch.FloatTensor(D_loss_list)).item()
    gen_loss_mean = torch.mean(torch.FloatTensor(G_loss_list)).item()
    print('Epoch: [%d/%d]: D_loss: %.3f, G_loss: %.3f' % (
        epoch, config["num_epochs"], discr_loss_mean,
        gen_loss_mean))

    if config["wandb"]:
        generated_image = denormalize(generator(fixed_noise))
        images = wandb.Image(generated_image, caption=f"epoch {epoch}")
        log = {
            "gen_loss": gen_loss_mean,
            "discr_loss": discr_loss_mean,
            "abs(gen_loss)": abs(gen_loss_mean),
            "abs(discr_loss)": abs(discr_loss_mean),
            "test images": images
        }
        if config["fid"]:
            fid_score = fid_score_generator(generator, model, config, denormalize=denormalize)
            log.update({
                "FID": fid_score
            })

        wandb.log(log)

    torch.save(generator.state_dict(), f"{config['save_path']}/generator_epoch_{epoch}.pth")
    torch.save(discriminator.state_dict(), f"{config['save_path']}/discriminator_epoch_{epoch}.pth")


